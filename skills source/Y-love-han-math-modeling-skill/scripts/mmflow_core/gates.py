from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, sha256_bytes, sha256_file
from .registry import Registry
from .reports import write_gate_report


VALID_CHECK_STATUSES = {"PASS", "FAIL", "ERROR", "BLOCKED", "NOT_APPLICABLE"}
SEVERITIES = {"CRITICAL", "MAJOR", "MODERATE", "MINOR"}


@dataclass(frozen=True)
class CheckResult:
    rule_id: str
    status: str
    severity: str
    reason: str
    evidence: list[str] = field(default_factory=list)
    rollback_stage: str | None = None
    invalidates: list[str] = field(default_factory=list)
    minimum_fix: list[str] = field(default_factory=list)
    rerun_scope: list[str] = field(default_factory=list)
    failed_entities: list[str] = field(default_factory=list)
    failed_paths: list[str] = field(default_factory=list)
    active_redline: str | None = None
    block: dict | None = None

    def validate(self) -> "CheckResult":
        if self.status not in VALID_CHECK_STATUSES:
            raise ValueError(f"unknown check status: {self.status}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity: {self.severity}")
        if not self.rule_id or not self.reason:
            raise ValueError("check requires rule_id and reason")
        if self.status == "NOT_APPLICABLE" and not self.evidence:
            raise ValueError("NOT_APPLICABLE requires structured evidence")
        if self.status == "BLOCKED" and not isinstance(self.block, dict):
            raise ValueError("BLOCKED requires a structured block payload")
        return self


def evidence_freshness(
    record: dict[str, Any],
    current_stage: str | None,
    current_epoch: int | None,
    stages_state: dict[str, str] | None,
    cross_stage: dict[str, list[str]] | None,
) -> dict[str, Any]:
    """Decide whether one evidence record is usable by the active gate.

    The evidence is fresh when it was registered in the current stage epoch,
    or when its evidence type is explicitly allowed to inherit across stages
    and its owning stage is currently PASSED in this workflow generation.
    A VALID status alone is never sufficient: future-stage evidence, evidence
    from a superseded epoch, and evidence whose owning stage was rolled back
    are all rejected.
    """
    stages_state = stages_state or {}
    cross_stage = cross_stage or {}
    created_stage = record.get("created_stage")
    stage_epoch = record.get("stage_epoch")
    if created_stage is None or stage_epoch is None:
        return {
            "current": False,
            "reason": "evidence predates stage-epoch metadata",
        }
    if created_stage == current_stage:
        if stage_epoch == current_epoch:
            return {"current": True, "reason": "same stage and epoch"}
        return {
            "current": False,
            "reason": (
                f"evidence epoch {stage_epoch} differs from current epoch "
                f"{current_epoch} for {current_stage}"
            ),
        }
    allowed_sources = cross_stage.get(str(record["payload"].get("evidence_type")), [])
    if created_stage not in allowed_sources:
        return {
            "current": False,
            "reason": (
                f"evidence created in {created_stage} is not allowed at "
                f"{current_stage}"
            ),
        }
    if stages_state.get(created_stage) != "PASSED":
        return {
            "current": False,
            "reason": (
                f"owning stage {created_stage} is not PASSED in this workflow "
                f"generation (status={stages_state.get(created_stage)})"
            ),
        }
    return {
        "current": True,
        "reason": f"cross-stage inheritance from passed {created_stage}",
    }


def aggregate_status(checks: list[CheckResult]) -> str:
    if not checks:
        return "ERROR"
    statuses = {check.status for check in checks}
    if "ERROR" in statuses:
        return "ERROR"
    if "FAIL" in statuses:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    return "PASS"


def evidence_fingerprint(registry: Registry, gate_id: str, policy_version: str) -> str:
    hashes: list[tuple[str, str, str]] = []
    for kind in (
        "artifact",
        "execution",
        "result",
        "claim",
        "formula",
        "figure",
        "citation",
        "finding",
        "evidence",
    ):
        for record in registry.iter_latest(kind):
            hashes.append((kind, record["entity_id"], record["record_sha256"]))
    return sha256_bytes(
        canonical_json_bytes(
            {
                "gate_id": gate_id,
                "policy_version": policy_version,
                "registry_records": sorted(hashes),
            }
        )
    )


def verify_gate_report(report: dict[str, Any], project_root: Path | str | None = None) -> bool:
    expected = report.get("report_sha256")
    body = {key: value for key, value in report.items() if key != "report_sha256"}
    if expected != sha256_bytes(canonical_json_bytes(body)):
        raise ValueError("gate report hash mismatch")
    if project_root is not None:
        root = Path(project_root).resolve()
        markdown = root / str(report.get("markdown_report_path", ""))
        json_path = root / str(report.get("json_report_path", ""))
        if not markdown.is_file() or sha256_file(markdown) != report.get("markdown_sha256"):
            raise ValueError("gate markdown report hash mismatch")
        if not json_path.is_file():
            raise ValueError("gate JSON report is missing")
    return True


class GateEngine:
    def __init__(self, project_root: Path | str, registry: Registry, policy_version: str) -> None:
        self.project_root = Path(project_root).resolve()
        self.registry = registry
        self.policy_version = policy_version

    def _evidence_checks(
        self, required: list[str], context: dict[str, Any]
    ) -> list[CheckResult]:
        current_stage = context.get("current_stage")
        current_epoch = context.get("stage_epoch")
        stages_state = context.get("stages_state") or {}
        cross_stage = context.get("cross_stage") or {}
        records: dict[str, list[dict[str, Any]]] = {}
        for record in self.registry.iter_latest("evidence"):
            payload = record["payload"]
            if payload.get("status") == "VALID":
                records.setdefault(str(payload.get("evidence_type")), []).append(record)
        checks: list[CheckResult] = []
        for evidence_type in required:
            candidates = records.get(evidence_type, [])
            if len(candidates) != 1:
                conflict_note = ""
                if len(candidates) > 1:
                    # 列出全部冲突实体及其所属 epoch，免去另行查询定位。
                    listed = sorted(
                        (
                            f"{record['entity_id']}"
                            f"(stage={record.get('created_stage')},"
                            f"epoch={record.get('stage_epoch')})"
                            for record in candidates
                        )
                    )
                    conflict_note = "; conflicting_entities=" + ",".join(listed)
                checks.append(
                    CheckResult(
                        rule_id=f"EVIDENCE-{evidence_type}",
                        status="FAIL",
                        severity="MAJOR",
                        reason=(
                            f"required exactly one current evidence {evidence_type}; "
                            f"actual={len(candidates)}"
                            + conflict_note
                            + (
                                "; NOTE: stage_epoch may have advanced after invalidate"
                                " — re-register ALL required evidence types for this stage"
                                " with fresh entity IDs in the current epoch"
                                if len(candidates) == 0
                                else (
                                    "; retire or invalidate all but one generation "
                                    "(mmflow retire-artifact / invalidate), then re-gate"
                                )
                            )
                        ),
                        minimum_fix=[
                            f"register one valid {evidence_type} evidence in this stage epoch"
                        ],
                    )
                )
                continue
            record = candidates[0]
            freshness = evidence_freshness(
                record,
                current_stage,
                current_epoch,
                stages_state,
                cross_stage,
            )
            if freshness["current"]:
                checks.append(
                    CheckResult(
                        rule_id=f"EVIDENCE-{evidence_type}",
                        status="PASS",
                        severity="MAJOR",
                        reason=(
                            f"evidence {evidence_type} is current, epoch-fresh, "
                            "and schema-valid"
                        ),
                        evidence=[record["entity_id"]],
                    )
                )
                continue
            checks.append(
                CheckResult(
                    rule_id=f"EVIDENCE-{evidence_type}",
                    status="FAIL",
                    severity="MAJOR",
                    reason=(
                        f"evidence {evidence_type} exists but is not fresh: "
                        f"{freshness['reason']}"
                    ),
                    failed_entities=[record["entity_id"]],
                    minimum_fix=[
                        "re-run the owning stage and register a new "
                        f"{evidence_type} evidence in the current epoch"
                    ],
                    rerun_scope=[str(current_stage)] if current_stage else [],
                )
            )
        return checks

    @staticmethod
    def _coerce_custom(rule_id: str, value: Any) -> CheckResult:
        if isinstance(value, CheckResult):
            return value.validate()
        if isinstance(value, dict):
            return CheckResult(
                rule_id=value.get("rule_id", rule_id),
                status=value.get("status", ""),
                severity=value.get("severity", "MAJOR"),
                reason=value.get("reason", "custom checker returned invalid result"),
                evidence=list(value.get("evidence", [])),
                rollback_stage=value.get("rollback_stage"),
                invalidates=list(value.get("invalidates", [])),
                minimum_fix=list(value.get("minimum_fix", [])),
                rerun_scope=list(value.get("rerun_scope", [])),
                failed_entities=list(value.get("failed_entities", [])),
                failed_paths=list(value.get("failed_paths", [])),
                active_redline=value.get("active_redline"),
                block=value.get("block"),
            ).validate()
        raise ValueError("custom checker must return CheckResult or dict")

    def run(
        self, gate_id: str, context: dict[str, Any], write_report: bool = False
    ) -> dict[str, Any]:
        required = context.get("required_evidence", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            required = []
            checks = [
                CheckResult(
                    "GATE-BAD-DEFINITION",
                    "ERROR",
                    "CRITICAL",
                    "required_evidence must be a list of strings",
                )
            ]
        else:
            checks = self._evidence_checks(required, context)
        active_redlines = context.get("active_redlines", [])
        if not isinstance(active_redlines, list):
            checks.append(
                CheckResult(
                    "GATE-BAD-REDLINES",
                    "ERROR",
                    "CRITICAL",
                    "active_redlines must be a list",
                )
            )
        else:
            for redline in sorted(set(active_redlines)):
                checks.append(
                    CheckResult(
                        rule_id=f"REDLINE-{redline}",
                        status="FAIL",
                        severity="CRITICAL",
                        reason=f"global redline remains active: {redline}",
                    )
                )
        custom_checks = context.get("custom_checks", [])
        if not isinstance(custom_checks, list):
            custom_checks = []
            checks.append(
                CheckResult(
                    "GATE-BAD-CHECKERS",
                    "ERROR",
                    "CRITICAL",
                    "custom_checks must be a list",
                )
            )
        for entry in custom_checks:
            try:
                rule_id, checker = entry
                checks.append(self._coerce_custom(rule_id, checker(context)))
            except Exception as error:
                rule_id = entry[0] if isinstance(entry, (list, tuple)) and entry else "UNKNOWN"
                checks.append(
                    CheckResult(
                        rule_id=str(rule_id),
                        status="ERROR",
                        severity="CRITICAL",
                        reason=f"checker exception: {type(error).__name__}: {error}",
                    )
                )
        if not checks:
            checks.append(
                CheckResult(
                    rule_id="GATE-NO-CHECKS",
                    status="ERROR",
                    severity="CRITICAL",
                    reason="gate loaded no checks; vacuous pass is forbidden",
                )
            )
        report: dict[str, Any] = {
            "gate_id": gate_id,
            "status": aggregate_status(checks),
            "policy_version": self.policy_version,
            "evidence_fingerprint": evidence_fingerprint(
                self.registry, gate_id, self.policy_version
            ),
            "checks": [asdict(check) for check in checks],
        }
        if write_report:
            report_directory = self.project_root / ".mmflow" / "reports"
            sequences: list[int] = []
            if report_directory.exists():
                for path in report_directory.glob("*.json"):
                    prefix = path.stem.split("_", 1)[0]
                    if prefix.isdigit():
                        sequences.append(int(prefix))
            sequence = max(sequences, default=0) + 1
            stem = f"{sequence:06d}_{gate_id}"
            report["json_report_path"] = f".mmflow/reports/{stem}.json"
            report["markdown_report_path"] = f".mmflow/reports/{stem}.md"
            json_path, markdown_path = write_gate_report(
                self.project_root, gate_id, sequence, report
            )
            if (
                json_path != report["json_report_path"]
                or markdown_path != report["markdown_report_path"]
            ):
                raise RuntimeError("gate report path calculation mismatch")
        return report
