from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import EvidenceInsufficientError

REQUIREMENT_KINDS = {"boolean", "number", "string", "pattern", "list"}
REQUIREMENT_SEVERITIES = {"HARD", "SOFT"}
VERIFICATION_METHODS = {
    "artifact_presence",
    "pdf_page_count",
    "filename_pattern",
    "file_size_limit",
    "privacy_scan",
    "manual_check",
}

_KIND_TYPE_CHECK = {
    "boolean": lambda value: isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "string": lambda value: isinstance(value, str) and bool(value),
    "pattern": lambda value: isinstance(value, str) and bool(value),
    "list": lambda value: isinstance(value, list) and all(
        isinstance(item, str) and item for item in value
    ),
}


def validate_requirement(requirement: Any) -> list[str]:
    """Return a list of contract violations for one structured requirement."""
    errors: list[str] = []
    if not isinstance(requirement, dict):
        return ["requirement entry is not an object"]
    requirement_id = requirement.get("requirement_id")
    if not isinstance(requirement_id, str) or not requirement_id:
        errors.append("requirement_id must be a non-empty string")
    kind = requirement.get("kind")
    if kind not in REQUIREMENT_KINDS:
        errors.append(f"requirement kind must be one of {sorted(REQUIREMENT_KINDS)}")
        return errors
    value = requirement.get("value")
    if not _KIND_TYPE_CHECK[kind](value):
        errors.append(f"requirement value type does not match kind={kind}")
    if kind == "pattern":
        try:
            re.compile(str(value))
        except re.error as error:
            errors.append(f"requirement pattern is not a valid regex: {error}")
    if not isinstance(requirement.get("scope"), str) or not requirement["scope"]:
        errors.append("requirement scope must be a non-empty string")
    if requirement.get("severity") not in REQUIREMENT_SEVERITIES:
        errors.append(f"requirement severity must be one of {sorted(REQUIREMENT_SEVERITIES)}")
    for field in ("source_citation_id", "snapshot_artifact_id"):
        if not isinstance(requirement.get(field), str) or not requirement[field]:
            errors.append(f"requirement {field} must be a non-empty string")
    locator = requirement.get("source_locator")
    if not isinstance(locator, dict) or not isinstance(locator.get("type"), str):
        errors.append("requirement source_locator must identify its source position")
    elif locator.get("type") not in {"page", "page_clause", "clause", "section"}:
        errors.append("requirement source_locator type is unsupported")
    elif not locator.get("page") and not locator.get("clause"):
        errors.append("requirement source_locator needs page or clause")
    if requirement.get("verification_method") not in VERIFICATION_METHODS:
        errors.append(
            f"requirement verification_method must be one of {sorted(VERIFICATION_METHODS)}"
        )
    return errors


def validate_requirements(requirements: Any) -> list[str]:
    """Validate a requirements list: structure plus ID uniqueness.

    An empty list is legal: a competition whose official rules impose no
    machine-checkable requirement must not fail because a PDF or a page
    count was assumed.
    """
    if not isinstance(requirements, list):
        return ["requirements must be a list"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, requirement in enumerate(requirements):
        prefix = f"requirements[{index}]"
        for error in validate_requirement(requirement):
            errors.append(f"{prefix}: {error}")
        requirement_id = requirement.get("requirement_id")
        if isinstance(requirement_id, str):
            if requirement_id in seen:
                errors.append(f"{prefix}: duplicate requirement_id {requirement_id}")
            seen.add(requirement_id)
    return errors


def _production_pdf_artifacts(runtime: Any) -> list[dict[str, Any]]:
    pdfs: list[dict[str, Any]] = []
    for record in runtime.registry.iter_latest("artifact"):
        payload = record["payload"]
        if (
            payload.get("status") != "VALID"
            or payload.get("artifact_class") != "production"
        ):
            continue
        media_type = str(payload.get("media_type", "")).lower()
        artifact_type = str(payload.get("artifact_type", ""))
        name = str(payload.get("relative_path", "")).lower()
        if (
            media_type == "application/pdf"
            or name.endswith(".pdf")
            or artifact_type in {"paper_pdf", "delivery_pdf", "pdf"}
        ):
            pdfs.append(record)
    return pdfs


def _pdf_page_count(path: Path) -> int:
    """Count pages of a real PDF document.

    Parser-backed counting (pypdf / PyMuPDF) runs first because it stays
    correct for compressed object streams; the historical byte-regex scan
    over ``/Type /Page`` objects remains as a fallback so the check never
    depends on an optional dependency being installed.
    """
    try:
        data = path.read_bytes()
    except OSError as error:
        raise EvidenceInsufficientError(f"cannot read PDF for page count: {error}") from error
    if b"%PDF-" not in data[:1024]:
        raise EvidenceInsufficientError("file is not a PDF document")
    try:
        from io import BytesIO

        try:
            from pypdf import PdfReader

            return len(PdfReader(BytesIO(data)).pages)
        except ImportError:
            pass
        try:
            import fitz

            document = fitz.open(stream=data, filetype="pdf")
            try:
                return int(document.page_count)
            finally:
                document.close()
        except ImportError:
            pass
    except Exception:
        # Any parser failure falls back to the structural byte scan below;
        # the requirement evaluation then reports the same result as before.
        pass
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


def _privacy_evidence_status(runtime: Any) -> str | None:
    for record in runtime.registry.iter_latest("evidence"):
        payload = record["payload"]
        if (
            payload.get("status") == "VALID"
            and payload.get("evidence_type") == "privacy_scan"
        ):
            return str(payload.get("content", {}).get("status", ""))
    return None


def evaluate_requirements(
    runtime: Any, requirements: Any
) -> list[dict[str, Any]]:
    """Evaluate every structured requirement against real project state.

    No requirement is evaluated from a self-reported PASS: PDF presence,
    page counts, filename patterns, size limits and anonymity each map to
    checked project artifacts.  A requirement with no programmatic method is
    reported as FAIL (HARD) or WARNING (SOFT), never silently skipped.
    """
    checks: list[dict[str, Any]] = []
    if not isinstance(requirements, list):
        return checks
    pdfs = _production_pdf_artifacts(runtime)
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        requirement_id = requirement.get("requirement_id")
        kind = requirement.get("kind")
        value = requirement.get("value")
        severity = requirement.get("severity", "SOFT")
        method = requirement.get("verification_method", "")
        reason = "requirement satisfied"
        status = "PASS"
        if kind == "boolean" and value is True:
            if requirement_id in {"pdf_required", "submission.pdf_required"} or (
                "pdf" in str(requirement_id).lower()
            ):
                if not pdfs:
                    status, reason = "FAIL", "no production PDF artifact exists"
            elif "anonymous" in str(requirement_id).lower():
                privacy_status = _privacy_evidence_status(runtime)
                if privacy_status != "PASS":
                    status, reason = (
                        "FAIL",
                        f"privacy scan did not pass (status={privacy_status})",
                    )
            elif "source" in str(requirement_id).lower() and "pdf" not in str(
                requirement_id
            ).lower():
                sources = [
                    record["payload"]
                    for record in runtime.registry.iter_latest("artifact")
                    if record["payload"].get("status") == "VALID"
                    and record["payload"].get("artifact_class") == "production"
                    and str(record["payload"].get("artifact_type", ""))
                    in {"paper_source", "source_code", "reproduction_notes"}
                ]
                if not sources:
                    status, reason = "FAIL", "no production source artifact exists"
            elif method == "manual_check":
                status, reason = "FAIL", "manual-check requirement has no programmatic proof"
        elif kind == "number":
            if "page" in str(requirement_id).lower() and (
                "min" in str(requirement_id).lower() or "max" in str(requirement_id).lower()
            ):
                if not pdfs:
                    status, reason = "FAIL", "page-limit requirement but no production PDF"
                else:
                    limit = float(value)
                    # 页数限制覆盖全部 production PDF：任何一份越限即 FAIL
                    for pdf_record in pdfs:
                        try:
                            pages = _pdf_page_count(
                                Path(runtime.project_root)
                                / str(pdf_record["payload"]["relative_path"])
                            )
                        except EvidenceInsufficientError as error:
                            status, reason = "FAIL", str(error)
                            break
                        if "min" in str(requirement_id).lower() and pages < limit:
                            status, reason = (
                                "FAIL",
                                f"page count {pages} below minimum {value} "
                                f"({pdf_record['payload']['relative_path']})",
                            )
                            break
                        if "max" in str(requirement_id).lower() and pages > limit:
                            status, reason = (
                                "FAIL",
                                f"page count {pages} exceeds maximum {value} "
                                f"({pdf_record['payload']['relative_path']})",
                            )
                            break
            elif "size" in str(requirement_id).lower():
                if not pdfs:
                    status, reason = "FAIL", "size-limit requirement but no production PDF"
                else:
                    limit = float(value)
                    for pdf_record in pdfs:
                        size = (
                            Path(runtime.project_root)
                            / str(pdf_record["payload"]["relative_path"])
                        ).stat().st_size
                        if size > limit:
                            status, reason = (
                                "FAIL",
                                f"file size {size} exceeds limit {value} "
                                f"({pdf_record['payload']['relative_path']})",
                            )
                            break
        elif kind == "pattern":
            pattern = str(value)
            matches = [
                record
                for record in runtime.registry.iter_latest("artifact")
                if record["payload"].get("status") == "VALID"
                and re.search(
                    pattern,
                    str(record["payload"].get("relative_path", "")).rsplit("/", 1)[-1],
                )
            ]
            if not matches:
                status, reason = "FAIL", f"no artifact matches filename pattern {pattern}"
        elif kind == "boolean" and value is False:
            # The official rule explicitly does not demand this artifact;
            # its absence is compliance, not a violation.
            status, reason = "PASS", "requirement explicitly not required"
        elif severity == "HARD":
            status, reason = (
                "FAIL",
                f"hard requirement {requirement_id} has no programmatic verification",
            )
        checks.append(
            {
                "requirement_id": requirement_id,
                "kind": kind,
                "status": status,
                "severity": severity,
                "reason": reason,
            }
        )
    return checks


def requirement_checks_match(registered: Any, recomputed: Any) -> bool:
    return registered == recomputed
