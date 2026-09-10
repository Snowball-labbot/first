from __future__ import annotations

from typing import Any

from .project import Runtime
from .quality import quality_contract_check

LABELS = (
    "NOT_READY",
    "REPRODUCIBLE",
    "QUALITY_REVIEW_READY",
    "SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW",
    "SPECIAL_PRIZE_CANDIDATE",
)

REVIEW_ROLES = (
    "competition_judge",
    "mathematics_numerics",
    "data_statistics",
    "reproducibility",
    "paper_compliance",
)


def _open_findings(runtime: Runtime) -> list[dict[str, Any]]:
    open_findings: list[dict[str, Any]] = []
    for record in runtime.registry.iter_latest("finding"):
        payload = record["payload"]
        if payload.get("status") == "VALID" and payload.get("finding_status") == "OPEN":
            open_findings.append(payload)
    return open_findings


def _review_modes(runtime: Runtime) -> dict[str, str]:
    modes: dict[str, str] = {}
    for record in runtime.registry.iter_latest("evidence"):
        payload = record["payload"]
        if (
            payload.get("status") != "VALID"
            or payload.get("evidence_type") != "review_report"
        ):
            continue
        content = payload.get("content")
        if not isinstance(content, dict):
            continue
        role = content.get("role")
        mode = content.get("reviewer_mode")
        if isinstance(role, str) and role in REVIEW_ROLES and isinstance(mode, str):
            modes.setdefault(role, mode)
    return modes


def compute_release_label(
    runtime: Runtime,
    *,
    integrity_ok: bool = True,
    tests_passed: bool = True,
) -> dict[str, Any]:
    """Compute the release label from program facts only.

    The caller cannot pass a label; every input is derived from the Registry,
    the workflow state, redlines and review evidence.  Any integrity failure,
    redline, open critical/major finding, or failing required test forces
    NOT_READY.

    When review roles are missing, the label distinguishes between
    REPRODUCIBLE (quality evidence not yet complete) and
    QUALITY_REVIEW_READY (quality evidence complete, awaiting professional
    review).  Without genuinely independent review the ceiling is
    SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW.
    """
    state = runtime.workflow.state()
    program_proven: list[str] = []
    caps: list[str] = []

    if not integrity_ok:
        caps.append("integrity_failure")
        return {
            "label": "NOT_READY",
            "program_proven": program_proven,
            "experiment_supported": [],
            "professional_judgments": [],
            "cannot_guarantee": ["prize_outcome", "judge_preference"],
            "caps": caps,
            "active_redlines": [],
            "reason": "registry or ledger integrity could not be verified",
        }
    if not tests_passed:
        caps.append("required_tests_failed")
        return {
            "label": "NOT_READY",
            "program_proven": program_proven,
            "experiment_supported": [],
            "professional_judgments": [],
            "cannot_guarantee": ["prize_outcome", "judge_preference"],
            "caps": caps,
            "active_redlines": [],
            "reason": "a required test or validator failed",
        }

    active_redlines: list[str] = []
    for record in runtime.registry.iter_latest("finding"):
        payload = record["payload"]
        if (
            payload.get("status") == "VALID"
            and payload.get("finding_status") == "OPEN"
            and isinstance(payload.get("redline_id"), str)
        ):
            redline = payload["redline_id"]
            if redline not in active_redlines:
                active_redlines.append(redline)
    if any(status in {"GATE_FAILED", "INTEGRITY_FAILURE"} for status in state["stages"].values()):
        caps.append("gate_failed")
        return {
            "label": "NOT_READY",
            "program_proven": program_proven,
            "experiment_supported": [],
            "professional_judgments": [],
            "cannot_guarantee": ["prize_outcome", "judge_preference"],
            "caps": caps,
            "active_redlines": active_redlines,
            "reason": "a stage gate failed or integrity is broken",
        }
    if active_redlines:
        caps.append("active_redline")
        return {
            "label": "NOT_READY",
            "program_proven": program_proven,
            "experiment_supported": [],
            "professional_judgments": [],
            "cannot_guarantee": ["prize_outcome", "judge_preference"],
            "caps": caps,
            "active_redlines": active_redlines,
            "reason": "an active redline forbids readiness",
        }
    open_findings = _open_findings(runtime)
    critical_or_major = [
        item for item in open_findings if item.get("severity") in {"CRITICAL", "MAJOR"}
    ]
    if critical_or_major:
        caps.append("open_critical_or_major_finding")
        return {
            "label": "NOT_READY",
            "program_proven": program_proven,
            "experiment_supported": [],
            "professional_judgments": [],
            "cannot_guarantee": ["prize_outcome", "judge_preference"],
            "caps": caps,
            "active_redlines": active_redlines,
            "reason": "open critical or major findings remain",
        }
    if state.get("complete") is not True:
        caps.append("workflow_incomplete")
        return {
            "label": "NOT_READY",
            "program_proven": program_proven,
            "experiment_supported": [],
            "professional_judgments": [],
            "cannot_guarantee": ["prize_outcome", "judge_preference"],
            "caps": caps,
            "active_redlines": active_redlines,
            "reason": "workflow is not COMPLETE",
        }

    program_proven.extend(
        [
            "p0_p11_passed",
            "hash_linked_ledger",
            "artifact_registry",
            "isolated_reproduction",
            "finding_closure_verified",
        ]
    )
    modes = _review_modes(runtime)
    missing_roles = sorted(set(REVIEW_ROLES) - set(modes))
    if missing_roles:
        caps.append("review_roles_incomplete")
        quality_result = quality_contract_check(runtime, "P11")
        if quality_result.status == "PASS":
            return {
                "label": "QUALITY_REVIEW_READY",
                "program_proven": program_proven,
                "experiment_supported": ["model_validation"],
                "professional_judgments": ["originality", "domain_significance"],
                "cannot_guarantee": ["prize_outcome", "judge_preference"],
                "caps": caps,
                "active_redlines": active_redlines,
                "reason": (
                    "quality evidence is complete but review roles are "
                    f"missing: {missing_roles}"
                ),
            }
        return {
            "label": "REPRODUCIBLE",
            "program_proven": program_proven,
            "experiment_supported": [],
            "professional_judgments": ["originality", "domain_significance"],
            "cannot_guarantee": ["prize_outcome", "judge_preference"],
            "caps": caps,
            "active_redlines": active_redlines,
            "reason": (
                f"review roles missing: {missing_roles}; "
                "quality evidence is not yet complete"
            ),
        }
    all_independent = all(
        modes[role] in {"independent_agent", "external_reviewer"} for role in REVIEW_ROLES
    )
    if all_independent:
        return {
            "label": "SPECIAL_PRIZE_CANDIDATE",
            "program_proven": program_proven,
            "experiment_supported": ["model_validation", "isolated_reproduction"],
            "professional_judgments": ["originality", "domain_significance"],
            "cannot_guarantee": ["prize_outcome", "judge_preference"],
            "caps": [],
            "active_redlines": active_redlines,
            "reason": "all gates passed and review was genuinely independent",
        }
    caps.append("independent_review_unavailable")
    return {
        "label": "SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW",
        "program_proven": program_proven,
        "experiment_supported": ["model_validation", "isolated_reproduction"],
        "professional_judgments": ["originality", "domain_significance"],
        "cannot_guarantee": ["prize_outcome", "judge_preference"],
        "caps": caps,
        "active_redlines": active_redlines,
        "reason": (
            "all gates passed but review independence is limited; "
            "the ceiling is SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW"
        ),
    }
