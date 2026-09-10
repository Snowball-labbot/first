from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


MANIFEST_NAME = "templates/template_manifest.json"
SCHEMA = "math-modeling-template-manifest/v1"
# Visualization templates are a first-class production surface.  Keeping the
# category explicit lets the manifest validator distinguish plotting assets
# from generic analytics snippets while applying the same evidence and
# controlled-execution rules.
CATEGORIES = {
    "production",
    "analytics",
    "publication",
    "presentation",
    "quality",
    "visualization",
}
STAGES = {f"P{i}" for i in range(12)}
EVIDENCE_TYPES = {
    "capability_report",
    "competition_rules",
    "policy_lock",
    "input_inventory",
    "selection_record",
    "requirement_matrix",
    "problem_contract",
    "data_lineage",
    "data_quality_report",
    "literature_registry",
    "leakage_audit",
    "baseline_protocol",
    "model_candidates",
    "validation_protocol",
    "frozen_analysis_plan",
    "production_execution",
    "structured_results",
    "validation_adapter_report",
    "degenerate_test",
    "counterevidence_report",
    "manuscript_source",
    "figure_registry",
    "citation_audit",
    "review_report",
    "delivery_manifest",
    "package_checksum",
    "privacy_scan",
    "quality_profile_selection",
    "theorem_application_record",
    "candidate_rejection_record",
    "formula_validity_record",
    "innovation_ablation_record",
    "counterintuitive_finding_record",
    "cross_problem_framework_record",
    "mechanism_explanation_record",
    "negative_result_record",
    "paper_depth_review",
    "special_prize_quality_assessment",
    "independent_review_provenance",
}


class TemplateManifestError(ValueError):
    """Raised when the template manifest cannot be trusted."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TemplateManifestError(f"cannot read JSON: {path}") from error
    if not isinstance(value, dict):
        raise TemplateManifestError(f"JSON root must be an object: {path}")
    return value


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = Path(value)
    return not candidate.is_absolute() and ".." not in candidate.parts


def _as_string_list(value: Any, field: str, errors: list[str], entry_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        errors.append(f"{entry_id}: {field} must be a list of non-empty strings")
        return []
    return list(value)


def validate_manifest(root: Path | str, manifest: dict[str, Any]) -> list[str]:
    root = Path(root).resolve()
    errors: list[str] = []
    if manifest.get("schema") != SCHEMA:
        errors.append(f"manifest schema must be {SCHEMA}")
    if manifest.get("version") != 1:
        errors.append("manifest version must be 1")
    entries = manifest.get("templates")
    if not isinstance(entries, list) or not entries:
        errors.append("manifest templates must be a non-empty list")
        return errors

    ids: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"template entry {index} must be an object")
            continue
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            errors.append(f"template entry {index} has no valid id")
            entry_id = f"entry-{index}"
        elif entry_id in ids:
            errors.append(f"duplicate template id: {entry_id}")
        ids.add(entry_id)

        category = entry.get("category")
        if category not in CATEGORIES:
            errors.append(f"{entry_id}: unsupported category: {category}")
        path = entry.get("path")
        if not _safe_relative_path(path):
            errors.append(f"{entry_id}: unsafe template path")
        elif not (root / path).is_file():
            errors.append(f"{entry_id}: template path does not exist: {path}")

        stages = _as_string_list(entry.get("stages"), "stages", errors, entry_id)
        if any(stage not in STAGES for stage in stages):
            errors.append(f"{entry_id}: stages must be P0-P11")
        _as_string_list(entry.get("inputs"), "inputs", errors, entry_id)
        _as_string_list(entry.get("outputs"), "outputs", errors, entry_id)
        evidence_types = _as_string_list(entry.get("evidence_types"), "evidence_types", errors, entry_id)
        if any(kind not in EVIDENCE_TYPES for kind in evidence_types):
            errors.append(f"{entry_id}: unsupported evidence type")
        # A visualization template is executable production scaffolding, not
        # evidence by itself.  It may therefore be production-eligible only
        # when the controlled runner later registers its actual output.
        if category not in {"production", "visualization"} and entry.get("production_eligible"):
            errors.append(f"{entry_id}: non-production template cannot be evidence")
        if not isinstance(entry.get("production_eligible", False), bool):
            errors.append(f"{entry_id}: production_eligible must be boolean")
        if not isinstance(entry.get("requires_controlled_execution", True), bool):
            errors.append(f"{entry_id}: requires_controlled_execution must be boolean")
        if entry.get("production_eligible") and not entry.get("evidence_types"):
            errors.append(f"{entry_id}: production template requires evidence_types")
    return errors


def load_manifest(root: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest = _load_json(root / MANIFEST_NAME)
    errors = validate_manifest(root, manifest)
    if errors:
        raise TemplateManifestError("; ".join(errors))
    return manifest


def resolve_template(root: Path | str, manifest: dict[str, Any], template_id: str) -> Path:
    root = Path(root).resolve()
    entry = next((item for item in manifest["templates"] if item.get("id") == template_id), None)
    if entry is None:
        raise TemplateManifestError(f"unknown template id: {template_id}")
    relative = entry["path"]
    if not _safe_relative_path(relative):
        raise TemplateManifestError(f"unsafe template path: {relative}")
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise TemplateManifestError(f"template escapes skill root: {relative}") from error
    if not path.is_file():
        raise TemplateManifestError(f"template file does not exist: {relative}")
    return path


def template_entry(manifest: dict[str, Any], template_id: str) -> dict[str, Any]:
    for entry in manifest["templates"]:
        if entry.get("id") == template_id:
            return entry
    raise TemplateManifestError(f"unknown template id: {template_id}")


def copy_template(
    root: Path | str,
    manifest: dict[str, Any],
    template_id: str,
    destination: Path | str,
    project_root: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    source = resolve_template(root, manifest, template_id)
    destination = Path(destination).resolve()
    if project_root is None:
        raise TemplateManifestError("--project-root is required for template copying")
    allowed_root = Path(project_root).resolve()
    if not allowed_root.exists():
        raise TemplateManifestError("project root must exist before copying a template")
    if not allowed_root.is_dir():
        raise TemplateManifestError("project root must be a directory")
    if allowed_root == root or root.is_relative_to(allowed_root):
        raise TemplateManifestError("project root cannot be the skill root or contain the skill root")
    if destination.exists():
        return {"status": "REFUSED", "reason": "destination exists", "destination": str(destination)}
    try:
        destination.relative_to(allowed_root)
    except ValueError as error:
        raise TemplateManifestError("destination must remain inside the declared project root") from error
    if ".mmflow" in destination.parts:
        raise TemplateManifestError("cannot copy into .mmflow")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {"status": "COPIED", "template_id": template_id, "destination": str(destination)}


def _report(root: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    try:
        manifest = load_manifest(root)
    except TemplateManifestError as error:
        return {"status": "FAIL", "template_count": 0, "errors": [str(error)]}
    return {
        "status": "PASS",
        "template_count": len(manifest["templates"]),
        "categories": sorted({entry["category"] for entry in manifest["templates"]}),
        "errors": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and inspect integrated modeling templates")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "list"):
        command = sub.add_parser(name)
        command.add_argument("--root", required=True)
        command.add_argument("--json", action="store_true")
    info = sub.add_parser("info")
    info.add_argument("template_id")
    info.add_argument("--root", required=True)
    copy = sub.add_parser("copy")
    copy.add_argument("template_id")
    copy.add_argument("destination")
    copy.add_argument("--root", required=True)
    copy.add_argument("--project-root")
    copy.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "check":
        report = _report(root)
    else:
        try:
            manifest = load_manifest(root)
        except TemplateManifestError as error:
            report = {"status": "FAIL", "errors": [str(error)]}
        else:
            if args.command == "list":
                report = {"status": "PASS", "templates": manifest["templates"]}
            elif args.command == "info":
                try:
                    report = template_entry(manifest, args.template_id)
                except TemplateManifestError as error:
                    print(str(error), file=sys.stderr)
                    return 2
            else:
                try:
                    report = copy_template(root, manifest, args.template_id, args.destination, args.project_root)
                except TemplateManifestError as error:
                    print(str(error), file=sys.stderr)
                    return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in {"PASS", "COPIED", "REFUSED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
