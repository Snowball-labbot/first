"""Adaptive scientific-depth quality contracts for the integrated skill.

The ordinary mmflow state machine remains the single source of truth.  This
module adds a profile-driven evidence contract on top of it: it never edits
workflow state and it never treats a score or label as a prize guarantee.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ConfigError, IntegrityError
from .gates import CheckResult


PROFILE_POLICY_NAME = "quality-profiles-v1.json"
APPLICABLE = "APPLICABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"
ALLOWED_APPLICABILITY = {APPLICABLE, NOT_APPLICABLE}
QUALITY_LABELS = {
    "NOT_READY",
    "REPRODUCIBLE",
    "QUALITY_REVIEW_READY",
    "SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW",
    "SPECIAL_PRIZE_CANDIDATE",
}


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
        and value not in (float("inf"), float("-inf"))
    )

SPECIAL_REVIEW_ROLES = {
    "competition_judge",
    "mathematics_numerics",
    "data_statistics",
    "reproducibility",
    "paper_compliance",
}


def load_quality_policy(skill_root: Path | str) -> dict[str, Any]:
    path = Path(skill_root).resolve() / "scripts" / "mmflow_core" / "policies" / PROFILE_POLICY_NAME
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IntegrityError(f"cannot load quality profile policy: {path}") from error
    if not isinstance(value, dict) or value.get("version") != 1:
        raise IntegrityError("quality profile policy is not version 1")
    profiles = value.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise IntegrityError("quality profile policy has no profiles")
    default = value.get("default")
    if not isinstance(default, str) or default not in profiles:
        raise IntegrityError("quality profile policy has an invalid default")
    return value


def _load_evidence_stage_matrix(skill_root: Path | str) -> dict[str, list[str]]:
    path = Path(skill_root).resolve() / "scripts" / "mmflow_core" / "policies" / "evidence-v1.json"
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IntegrityError(f"cannot load evidence stage policy: {path}") from error
    matrix = value.get("evidence_stage_matrix") if isinstance(value, dict) else None
    if not isinstance(matrix, dict):
        raise IntegrityError("evidence stage policy has no evidence_stage_matrix")
    return {
        str(evidence_type): [str(stage) for stage in stages]
        for evidence_type, stages in matrix.items()
        if isinstance(evidence_type, str) and isinstance(stages, list)
    }


def profile_names(skill_root: Path | str) -> set[str]:
    return set(load_quality_policy(skill_root)["profiles"])


def normalize_profile(skill_root: Path | str, profile: str | None) -> str:
    policy = load_quality_policy(skill_root)
    selected = profile or str(policy["default"])
    if selected not in policy["profiles"]:
        raise ConfigError(
            f"unknown quality profile {selected!r}; choose one of "
            + ", ".join(sorted(policy["profiles"]))
        )
    return selected


def selected_profile(runtime: Any) -> str:
    # Small policy-only test doubles may expose only ``contract``.  Resolve
    # the policy beside this module in that case; real Runtime objects always
    # carry the immutable skill_root explicitly.
    skill_root = getattr(runtime, "skill_root", Path(__file__).resolve().parents[2])
    policy = load_quality_policy(skill_root)
    contract = getattr(runtime, "contract", None)
    if not isinstance(contract, dict):
        raise ConfigError("runtime contract must be an object")
    profile = contract.get("quality_profile") or policy["default"]
    if not isinstance(profile, str) or profile not in policy["profiles"]:
        raise ConfigError(f"project quality_profile is invalid: {profile!r}")
    return profile


def _stage_index(stage: str) -> int:
    if not isinstance(stage, str) or len(stage) < 2 or stage[0] != "P":
        raise ConfigError(f"invalid stage: {stage!r}")
    try:
        return int(stage[1:])
    except ValueError as error:
        raise ConfigError(f"invalid stage: {stage!r}") from error


def _records(runtime: Any) -> dict[str, list[dict[str, Any]]]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for record in runtime.registry.iter_latest("evidence"):
        if not isinstance(record, dict):
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("status") != "VALID":
            continue
        evidence_type = payload.get("evidence_type")
        if isinstance(evidence_type, str):
            by_type.setdefault(evidence_type, []).append(record)
    return by_type


def _list_field(content: dict[str, Any], field: str, *, nonempty: bool = False) -> list[Any]:
    value = content.get(field)
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if nonempty and not value:
        raise ValueError(f"{field} must not be empty")
    return value


def _validate_string_list(
    value: Any,
    field: str,
    *,
    nonempty: bool = False,
) -> list[str]:
    """Validate a JSON list whose members must be non-empty strings.

    Quality evidence is user-authored JSON.  Keeping this check separate from
    the set/comparison logic below prevents malformed list/dict members from
    escaping into hash-based comparisons and turning a quality failure into a
    validator crash.
    """

    if not isinstance(value, list):
        return [f"{field} must be a list"]
    errors: list[str] = []
    if nonempty and not value:
        errors.append(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{field} must contain only non-empty strings")
    return errors


def _valid_string_list(value: Any, *, nonempty: bool = False) -> bool:
    return not _validate_string_list(value, "value", nonempty=nonempty)


def _safe_workflow_snapshot(runtime: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """Read a workflow snapshot without allowing corrupt state to crash QA.

    A project registry can contain user-authored or partially recovered data.
    Quality validation must turn a malformed snapshot into an explicit
    integrity finding, while preserving the normal Runtime behavior.
    """

    workflow = getattr(runtime, "workflow", None)
    snapshot_fn = getattr(workflow, "snapshot", None)
    if not callable(snapshot_fn):
        return None, ["workflow snapshot is unavailable"]
    try:
        snapshot = snapshot_fn()
    except Exception as error:
        return None, [f"workflow snapshot could not be read: {error}"]
    if not isinstance(snapshot, dict):
        return None, ["workflow snapshot must be an object"]
    return snapshot, []


def _validate_common_depth_content(content: Any) -> list[str]:
    if not isinstance(content, dict):
        return ["content must be an object"]
    errors: list[str] = []
    applicability = content.get("applicability")
    if not isinstance(applicability, str) or applicability not in ALLOWED_APPLICABILITY:
        errors.append("applicability must be APPLICABLE or NOT_APPLICABLE")
    for field in (
        "source_entity_ids",
        "supported_claim_ids",
        "alternative_evidence_ids",
        "problem_ids",
    ):
        errors.extend(
            _validate_string_list(
                content.get(field),
                field,
                nonempty=field == "problem_ids" and applicability == APPLICABLE,
            )
        )
    for field in ("checks", "limitations"):
        try:
            _list_field(content, field, nonempty=True)
        except ValueError as error:
            errors.append(str(error))
    for field in ("method", "reviewer"):
        if not isinstance(content.get(field), str) or not content[field].strip():
            errors.append(f"{field} must be a non-empty string")
    reason = content.get("not_applicable_reason")
    alternatives = content.get("alternative_evidence_ids")
    detail = content.get("not_applicable_detail")
    if applicability == NOT_APPLICABLE:
        if not isinstance(reason, str) or not reason.strip():
            errors.append("NOT_APPLICABLE requires not_applicable_reason")
        alternative_required = True
        if not isinstance(detail, dict):
            errors.append(
                "NOT_APPLICABLE requires a structured not_applicable_detail object "
                "with basis, quality_impact and alternative_required"
            )
        else:
            for key in ("basis", "quality_impact"):
                value = detail.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"not_applicable_detail.{key} must be a non-empty string")
            flag = detail.get("alternative_required")
            if not isinstance(flag, bool):
                errors.append("not_applicable_detail.alternative_required must be a boolean")
            else:
                alternative_required = flag
        if alternative_required:
            if not isinstance(alternatives, list) or not alternatives:
                errors.append("NOT_APPLICABLE requires alternative_evidence_ids")
        elif isinstance(alternatives, list) and alternatives:
            errors.append(
                "alternative_required is false, so alternative_evidence_ids must stay empty"
            )
    else:
        if reason not in (None, ""):
            errors.append("APPLICABLE evidence must leave not_applicable_reason empty")
        if detail not in (None, ""):
            errors.append("APPLICABLE evidence must leave not_applicable_detail empty")
    return errors


def _validate_special_assessment(
    content: Any,
    profile_definition: dict[str, Any] | None = None,
    runtime: Any | None = None,
    current_stage: str | None = None,
) -> list[str]:
    if not isinstance(content, dict):
        return ["content must be an object"]
    errors = _validate_common_depth_content(content)
    level = content.get("level")
    if not isinstance(level, str) or level not in QUALITY_LABELS:
        errors.append("special-prize assessment has an invalid level")
    for field in ("program_facts", "experiment_supported", "professional_judgments", "cannot_guarantee"):
        errors.extend(_validate_string_list(content.get(field), field, nonempty=True))
    cannot_values = content.get("cannot_guarantee")
    cannot = {
        item for item in cannot_values
        if isinstance(item, str)
    } if isinstance(cannot_values, list) else set()
    if not {"prize_outcome", "judge_preference"}.issubset(cannot):
        errors.append("special-prize assessment must disclose prize_outcome and judge_preference limits")
    # v1 test doubles and already-created adaptive fixtures do not carry an
    # immutable skill_root.  Keep their historical structural compatibility;
    # every real Runtime (and therefore every deliverable project) uses the
    # strict criterion/evidence recomputation below.
    if runtime is not None and not hasattr(runtime, "skill_root"):
        return errors
    if profile_definition is not None and not isinstance(profile_definition, dict):
        errors.append("quality profile definition must be an object")
        return errors
    score_policy = (profile_definition or {}).get("score_policy", {})
    # Only the special-prize profile defines the auditable numeric score.
    # Other depth profiles reuse the qualitative assessment record without
    # acquiring a score contract they did not select.
    if not score_policy:
        # M-Q14: a profile without a score contract may still submit a
        # qualitative assessment, but it must never self-declare a
        # SPECIAL_PRIZE candidate label - that label is reserved for the
        # auditable nine-criterion score plus independent review provenance.
        if isinstance(level, str) and level.startswith("SPECIAL_PRIZE"):
            errors.append(
                "assessment claims a SPECIAL_PRIZE label without an "
                "auditable score_policy; re-register under the special-prize "
                "profile or lower the declared level"
            )
        return errors
    if not isinstance(score_policy, dict):
        errors.append("special-prize score policy must be an object")
        return errors
    criteria = content.get("criterion_results")
    policy_criteria = score_policy.get("criteria", [])
    if not isinstance(criteria, list):
        errors.append("special-prize assessment requires criterion_results")
        return errors
    if not isinstance(policy_criteria, list) or not policy_criteria:
        errors.append("special-prize score policy has no criteria")
        return errors
    expected: dict[str, dict[str, Any]] = {}
    for policy_item in policy_criteria:
        identifier = policy_item.get("id") if isinstance(policy_item, dict) else None
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append("special-prize score policy criteria require non-empty string IDs")
            continue
        if identifier in expected:
            errors.append(f"special-prize score policy duplicates criterion: {identifier}")
            continue
        expected[identifier] = policy_item
    if not expected:
        errors.append("special-prize score policy has no valid criteria")
        return errors
    observed: dict[str, dict[str, Any]] = {}
    for item in criteria:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            errors.append("each criterion_result requires a string id")
            continue
        identifier = item["id"]
        if not identifier.strip():
            errors.append("each criterion_result requires a non-empty string id")
            continue
        if identifier in observed or identifier not in expected:
            errors.append(f"unknown or duplicated special-prize criterion: {identifier}")
            continue
        observed[identifier] = item
        status = item.get("status")
        if not isinstance(status, str) or status not in {"PASS", "PARTIAL", "FAIL", NOT_APPLICABLE}:
            errors.append(f"criterion {identifier} has an invalid status")
        evidence_ids = item.get("evidence_ids")
        if not isinstance(evidence_ids, list):
            errors.append(f"criterion {identifier} requires evidence_ids")
        elif not _valid_string_list(evidence_ids):
            errors.append(f"criterion {identifier} evidence_ids must contain non-empty strings")
        if not _is_finite_number(item.get("earned")):
            errors.append(f"criterion {identifier} requires a numeric earned field")
    if set(observed) != set(expected):
        errors.append("special-prize criterion_results must cover every policy criterion exactly once")
    score_total = 0.0
    for identifier, policy_item in expected.items():
        item = observed.get(identifier)
        if item is None:
            continue
        try:
            maximum = float(policy_item.get("maximum", 0.0))
        except (TypeError, ValueError):
            errors.append(f"criterion {identifier} has an invalid policy maximum")
            continue
        if not _is_finite_number(maximum) or maximum < 0:
            errors.append(f"criterion {identifier} has an invalid policy maximum")
            continue
        status = item.get("status")
        if not isinstance(status, str):
            continue
        expected_score = {
            "PASS": maximum,
            "PARTIAL": maximum * 0.5,
            "FAIL": 0.0,
            NOT_APPLICABLE: 0.0,
        }.get(status)
        if expected_score is None:
            continue
        try:
            earned = float(item.get("earned"))
        except (TypeError, ValueError):
            continue
        if earned != expected_score:
            errors.append(
                f"criterion {identifier} earned={earned} conflicts with policy-derived score {expected_score}"
            )
        if status == NOT_APPLICABLE:
            alternatives = item.get("alternative_evidence_ids")
            if not isinstance(alternatives, list) or not alternatives:
                errors.append(f"NOT_APPLICABLE criterion {identifier} requires alternative_evidence_ids")
            elif not _valid_string_list(alternatives):
                errors.append(
                    f"NOT_APPLICABLE criterion {identifier} alternative_evidence_ids "
                    "must contain non-empty strings"
                )
            elif runtime is not None:
                for alternative in alternatives:
                    try:
                        alternative_record = runtime.registry.find_entity(alternative)
                    except Exception:
                        errors.append(
                            f"NOT_APPLICABLE criterion {identifier} references unknown "
                            f"alternative evidence: {alternative}"
                        )
                        continue
                    if not isinstance(alternative_record, dict):
                        errors.append(
                            f"NOT_APPLICABLE criterion {identifier} alternative evidence "
                            f"is malformed: {alternative}"
                        )
                        continue
                    alternative_payload = alternative_record.get("payload")
                    if (
                        alternative_record.get("entity_kind") != "evidence"
                        or not isinstance(alternative_payload, dict)
                        or alternative_payload.get("status") != "VALID"
                    ):
                        errors.append(
                            f"NOT_APPLICABLE criterion {identifier} alternative evidence "
                            f"is not VALID: {alternative}"
                        )
        else:
            allowed_types_value = policy_item.get("allowed_evidence_types", [])
            allowed_types = {
                item for item in allowed_types_value
                if isinstance(item, str)
            } if isinstance(allowed_types_value, list) else set()
            if (
                not isinstance(allowed_types_value, list)
                or any(not isinstance(item, str) or not item.strip() for item in allowed_types_value)
            ):
                errors.append(f"criterion {identifier} has invalid allowed_evidence_types in policy")
            evidence_ids = item.get("evidence_ids", [])
            if not evidence_ids:
                errors.append(f"criterion {identifier} requires at least one evidence ID")
            if runtime is not None and _valid_string_list(evidence_ids, nonempty=True):
                for evidence_id in evidence_ids:
                    try:
                        evidence_record = runtime.registry.find_entity(evidence_id)
                    except Exception:
                        errors.append(f"criterion {identifier} references unknown evidence: {evidence_id}")
                        continue
                    if not isinstance(evidence_record, dict):
                        errors.append(f"criterion {identifier} evidence is malformed: {evidence_id}")
                        continue
                    payload = evidence_record.get("payload")
                    if not isinstance(payload, dict):
                        errors.append(f"criterion {identifier} evidence is malformed: {evidence_id}")
                        continue
                    if evidence_record.get("entity_kind") != "evidence" or payload.get("status") != "VALID":
                        errors.append(f"criterion {identifier} evidence is not VALID: {evidence_id}")
                    if payload.get("evidence_type") not in allowed_types:
                        errors.append(
                            f"criterion {identifier} evidence {evidence_id} has type "
                            f"{payload.get('evidence_type')} outside the score policy"
                        )
                    if hasattr(runtime, "skill_root"):
                        evidence_stage = evidence_record.get("created_stage")
                        evidence_epoch = evidence_record.get("stage_epoch")
                        snapshot, snapshot_errors = _safe_workflow_snapshot(runtime)
                        errors.extend(snapshot_errors)
                        if snapshot is None:
                            continue
                        stage_epochs = snapshot.get("stage_epochs")
                        stages = snapshot.get("stages")
                        if not isinstance(stage_epochs, dict):
                            errors.append("workflow snapshot stage_epochs must be an object")
                            continue
                        if not isinstance(stages, dict):
                            errors.append("workflow snapshot stages must be an object")
                            continue
                        if not isinstance(evidence_stage, str):
                            errors.append(
                                f"criterion {identifier} evidence {evidence_id} has an invalid owning stage"
                            )
                            continue
                        current_epoch = stage_epochs.get(evidence_stage)
                        allowed_stages = _load_evidence_stage_matrix(runtime.skill_root).get(
                            str(payload.get("evidence_type")), []
                        )
                        target_stage = current_stage or "P10"
                        if evidence_stage not in allowed_stages:
                            errors.append(
                                f"criterion {identifier} evidence {evidence_id} is outside its stage matrix"
                            )
                        if evidence_epoch != current_epoch:
                            errors.append(
                                f"criterion {identifier} evidence {evidence_id} is not epoch-current"
                            )
                        elif evidence_stage != target_stage and stages.get(evidence_stage) != "PASSED":
                            errors.append(
                                f"criterion {identifier} evidence {evidence_id} owning stage is not PASSED"
                            )
        score_total += expected_score
    declared_total = content.get("total")
    if not _is_finite_number(declared_total) or float(declared_total) != score_total:
        errors.append(
            f"special-prize total={declared_total} conflicts with policy-derived total {score_total}"
        )
    try:
        threshold = float(score_policy.get("candidate_threshold", 90.0))
    except (TypeError, ValueError):
        errors.append("special-prize score policy has an invalid candidate_threshold")
        threshold = 90.0
    if not _is_finite_number(threshold) or threshold < 0:
        errors.append("special-prize score policy has an invalid candidate_threshold")
        threshold = 90.0
    level = content.get("level")
    if level == "SPECIAL_PRIZE_CANDIDATE" and score_total < threshold:
        errors.append("SPECIAL_PRIZE_CANDIDATE level requires the policy score threshold")
    if level == "SPECIAL_PRIZE_CANDIDATE" and runtime is not None:
        provenance = [
            record for record in runtime.registry.iter_latest("evidence")
            if isinstance(record, dict)
            and isinstance(record.get("payload"), dict)
            and record["payload"].get("status") == "VALID"
            and record["payload"].get("evidence_type") == "independent_review_provenance"
        ]
        if len(provenance) != 1:
            errors.append("SPECIAL_PRIZE_CANDIDATE requires one VALID independent_review_provenance evidence")
    return errors


def _validate_profile_selection(content: Any, profile: str) -> list[str]:
    if not isinstance(content, dict):
        return ["profile selection content must be an object"]
    errors: list[str] = []
    if content.get("profile") != profile:
        errors.append("profile selection differs from the project contract")
    if not isinstance(content.get("selected_at"), str) or not content["selected_at"].strip():
        errors.append("profile selection requires selected_at")
    if not isinstance(content.get("rationale"), str) or not content["rationale"].strip():
        errors.append("profile selection requires a rationale")
    if content.get("frozen_with_analysis_plan") is not True:
        errors.append("profile selection must be frozen with the analysis plan")
    return errors


def _validate_independent_provenance(content: Any, runtime: Any) -> list[str]:
    if not isinstance(content, dict):
        return ["independent review provenance content must be an object"]
    errors: list[str] = []
    reviewers = content.get("reviewers")
    if not isinstance(reviewers, list) or not reviewers:
        return ["independent review provenance requires reviewers"]
    seen_roles: set[str] = set()
    seen_execution_ids: set[str] = set()
    for reviewer in reviewers:
        if not isinstance(reviewer, dict):
            errors.append("reviewer provenance entries must be objects")
            continue
        role = reviewer.get("role")
        role_is_valid = (
            isinstance(role, str)
            and bool(role.strip())
            and role in SPECIAL_REVIEW_ROLES
        )
        if not role_is_valid or (isinstance(role, str) and role in seen_roles):
            errors.append(f"reviewer provenance has an invalid or duplicated role: {role}")
        if role_is_valid:
            seen_roles.add(role)
        review_mode = reviewer.get("review_mode")
        if not isinstance(review_mode, str) or review_mode not in {"independent_agent", "external_reviewer"}:
            errors.append(f"reviewer {role} is not independently executed")
        execution_id = reviewer.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id.strip():
            errors.append(f"reviewer {role} requires an execution_id")
            continue
        if execution_id in seen_execution_ids:
            errors.append(
                f"reviewer {role} reuses an execution; independent roles require distinct executions"
            )
        seen_execution_ids.add(execution_id)
        try:
            execution_record = runtime.registry.latest("execution", execution_id)
        except Exception:
            errors.append(f"reviewer {role} references an unknown execution")
            continue
        if not isinstance(execution_record, dict):
            errors.append(f"reviewer {role} execution record is malformed")
            continue
        execution = execution_record.get("payload")
        if not isinstance(execution, dict):
            errors.append(f"reviewer {role} execution payload is malformed")
            continue
        execution_role_is_valid = (
            role_is_valid
            and execution.get("role") in {role, f"review:{role}"}
        )
        if (
            execution_record.get("entity_kind") != "execution"
            or execution.get("status") != "VALID"
            or execution.get("artifact_class") != "production"
            or execution.get("stage") != "P10"
            or execution.get("exit_code") != 0
            or not execution_role_is_valid
        ):
            errors.append(f"reviewer {role} execution is not a valid P10 production execution")
        input_ids = reviewer.get("input_artifact_ids")
        output_ids = reviewer.get("output_artifact_ids")
        if not isinstance(input_ids, list) or not isinstance(output_ids, list) or not output_ids:
            errors.append(f"reviewer {role} must declare input and non-empty output artifact IDs")
        else:
            input_ids_valid = _valid_string_list(input_ids)
            output_ids_valid = _valid_string_list(output_ids, nonempty=True)
            if not input_ids_valid or not output_ids_valid:
                errors.append(f"reviewer {role} artifact IDs must contain only non-empty strings")
            if input_ids_valid and len(input_ids) != len(set(input_ids)):
                errors.append(f"reviewer {role} input artifact IDs must be unique")
            if output_ids_valid and len(output_ids) != len(set(output_ids)):
                errors.append(f"reviewer {role} output artifact IDs must be unique")
            source_ids = execution.get("source_artifact_ids")
            source_ids_valid = _valid_string_list(source_ids)
            if not source_ids_valid:
                errors.append(f"reviewer {role} execution source_artifact_ids must contain only non-empty strings")
            elif len(source_ids) != len(set(source_ids)):
                errors.append(f"reviewer {role} execution source_artifact_ids must be unique")
            if input_ids_valid and source_ids_valid and set(input_ids) != set(source_ids):
                errors.append(f"reviewer {role} input closure differs from execution sources")
            if input_ids_valid:
                for artifact_id in input_ids:
                    try:
                        artifact_record = runtime.registry.find_entity(artifact_id)
                    except Exception:
                        errors.append(f"reviewer {role} references an unknown input artifact: {artifact_id}")
                        continue
                    if not isinstance(artifact_record, dict):
                        errors.append(f"reviewer {role} input artifact is malformed: {artifact_id}")
                        continue
                    artifact_payload = artifact_record.get("payload")
                    if (
                        artifact_record.get("entity_kind") != "artifact"
                        or not isinstance(artifact_payload, dict)
                        or artifact_payload.get("status") != "VALID"
                    ):
                        errors.append(f"reviewer {role} input artifact is not VALID: {artifact_id}")
            if output_ids_valid:
                produced: set[str] = set()
                for item in runtime.registry.iter_latest("artifact"):
                    if not isinstance(item, dict):
                        continue
                    item_payload = item.get("payload")
                    if not isinstance(item_payload, dict):
                        continue
                    if (
                        item_payload.get("execution_id") == execution_id
                        and item_payload.get("status") == "VALID"
                        and item_payload.get("artifact_class") == "production"
                    ):
                        artifact_entity_id = item.get("entity_id")
                        if isinstance(artifact_entity_id, str) and artifact_entity_id.strip():
                            produced.add(artifact_entity_id)
                        else:
                            errors.append(f"reviewer {role} has a production artifact without a valid entity_id")
                if set(output_ids) != produced:
                    errors.append(f"reviewer {role} output closure differs from execution outputs")
                for artifact_id in output_ids:
                    try:
                        artifact_record = runtime.registry.find_entity(artifact_id)
                    except Exception:
                        errors.append(f"reviewer {role} references an unknown output artifact: {artifact_id}")
                        continue
                    if not isinstance(artifact_record, dict):
                        errors.append(f"reviewer {role} output artifact is malformed: {artifact_id}")
                        continue
                    artifact_payload = artifact_record.get("payload")
                    if (
                        artifact_record.get("entity_kind") != "artifact"
                        or not isinstance(artifact_payload, dict)
                        or artifact_payload.get("status") != "VALID"
                        or artifact_payload.get("artifact_class") != "production"
                        or artifact_payload.get("execution_id") != execution_id
                    ):
                        errors.append(f"reviewer {role} output artifact is not a VALID production output: {artifact_id}")
        checks = reviewer.get("independence_checks")
        required_checks = {"distinct_execution", "input_closure", "blind_context", "post_p8"}
        if not isinstance(checks, list):
            errors.append(f"reviewer {role} independence_checks must be a list")
        else:
            check_map: dict[str, Any] = {}
            for item in checks:
                if not isinstance(item, dict):
                    errors.append(f"reviewer {role} independence_checks entries must be objects")
                    continue
                identifier = item.get("id")
                if not isinstance(identifier, str) or not identifier.strip():
                    errors.append(f"reviewer {role} independence_checks IDs must be non-empty strings")
                    continue
                if identifier in check_map:
                    errors.append(f"reviewer {role} independence_checks IDs must be unique")
                    continue
                check_map[identifier] = item.get("status")
            if any(check_map.get(identifier) != "PASS" for identifier in required_checks):
                errors.append(f"reviewer {role} lacks PASS provenance checks")
        if hasattr(runtime, "skill_root"):
            snapshot, snapshot_errors = _safe_workflow_snapshot(runtime)
            errors.extend(snapshot_errors)
            stages = snapshot.get("stages") if snapshot is not None else None
            if not isinstance(stages, dict):
                errors.append("workflow stages must be an object")
            elif stages.get("P8") != "PASSED":
                errors.append(f"reviewer {role} execution is not post-P8 in the current workflow")
    if seen_roles != SPECIAL_REVIEW_ROLES:
        errors.append("independent review provenance must cover all five review roles")
    limitations = content.get("limitations")
    errors.extend(_validate_string_list(limitations, "limitations", nonempty=True))
    return errors


def _record_error(
    record: dict[str, Any],
    expected_stage: str,
    profile: str,
    runtime: Any,
    *,
    current_stage: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["evidence record must be an object"]
    if record.get("created_stage") != expected_stage:
        errors.append(
            f"{record.get('entity_id')} must be created at {expected_stage}, "
            f"not {record.get('created_stage')}"
        )
    if not isinstance(record.get("created_ledger_sequence"), int):
        errors.append(f"{record.get('entity_id')} has no ledger sequence")
    # A real project Runtime is bound to an immutable workflow generation.
    # VALID status alone cannot revive depth evidence from a superseded epoch.
    if hasattr(runtime, "skill_root"):
        snapshot, snapshot_errors = _safe_workflow_snapshot(runtime)
        errors.extend(snapshot_errors)
        if not isinstance(snapshot, dict):
            if not snapshot_errors:
                errors.append("workflow snapshot is unavailable for evidence freshness")
        else:
            stage_epochs = snapshot.get("stage_epochs", {})
            if not isinstance(stage_epochs, dict):
                errors.append("workflow snapshot stage_epochs must be an object")
                stage_epochs = {}
            expected_epoch = stage_epochs.get(expected_stage)
            if record.get("stage_epoch") != expected_epoch:
                errors.append(
                    f"{record.get('entity_id')} evidence epoch {record.get('stage_epoch')} "
                    f"is stale; current {expected_stage} epoch is {expected_epoch}"
                )
            if current_stage is not None and expected_stage != current_stage:
                stages = snapshot.get("stages", {})
                if not isinstance(stages, dict):
                    errors.append("workflow snapshot stages must be an object")
                elif stages.get(expected_stage) != "PASSED":
                    errors.append(
                        f"{record.get('entity_id')} owning stage {expected_stage} "
                        f"is not PASSED before {current_stage}"
                    )
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return errors + [f"{record.get('entity_id')} evidence payload must be an object"]
    content = payload.get("content")
    evidence_type = payload.get("evidence_type")
    if evidence_type == "quality_profile_selection":
        errors.extend(_validate_profile_selection(content, profile))
    elif evidence_type == "special_prize_quality_assessment":
        policy = load_quality_policy(runtime.skill_root if hasattr(runtime, "skill_root") else Path(__file__).resolve().parents[2])
        errors.extend(
            _validate_special_assessment(
                content,
                policy["profiles"].get(profile, {}),
                runtime,
                current_stage,
            )
        )
    elif evidence_type == "independent_review_provenance":
        errors.extend(_validate_independent_provenance(content, runtime))
    else:
        errors.extend(_validate_common_depth_content(content))
    return errors


def _check_item(
    by_type: dict[str, list[dict[str, Any]]],
    evidence_type: str,
    expected_stage: str,
    profile: str,
    runtime: Any,
    *,
    core: bool,
    current_stage: str | None = None,
) -> list[str]:
    records = by_type.get(evidence_type, [])
    if len(records) != 1:
        return [
            f"{profile} requires exactly one VALID {evidence_type} evidence "
            f"created at {expected_stage}; actual={len(records)}"
        ]
    record = records[0]
    errors = _record_error(
        record,
        expected_stage,
        profile,
        runtime,
        current_stage=current_stage,
    )
    if not isinstance(record, dict):
        return errors + ["evidence record must be an object"]
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return errors + [f"{record.get('entity_id')} evidence payload must be an object"]
    content = payload.get("content")
    if isinstance(content, dict) and content.get("applicability") == NOT_APPLICABLE:
        if core:
            errors.append(f"core evidence {evidence_type} cannot be NOT_APPLICABLE")
        else:
            detail = content.get("not_applicable_detail")
            alternative_required = True
            if isinstance(detail, dict) and isinstance(
                detail.get("alternative_required"), bool
            ):
                alternative_required = detail["alternative_required"]
            alternatives = content.get("alternative_evidence_ids", [])
            if not alternative_required and not alternatives:
                # A justified NOT_APPLICABLE decision may declare that no
                # alternative verification applies; _validate_common_depth_content
                # already rejects mixing this flag with listed alternatives.
                return errors
            if not _valid_string_list(alternatives, nonempty=True):
                errors.append(
                    f"alternative evidence IDs for {evidence_type} must contain non-empty strings"
                )
                alternatives = []
            for alternative in alternatives:
                try:
                    alternative_record = next(
                        item
                        for records_for_type in by_type.values()
                        for item in records_for_type
                        if isinstance(item, dict) and item.get("entity_id") == alternative
                    )
                except StopIteration:
                    errors.append(f"alternative evidence is unknown: {alternative}")
                    continue
                alternative_payload = alternative_record.get("payload")
                if (
                    not isinstance(alternative_payload, dict)
                    or alternative_record.get("entity_kind") != "evidence"
                    or alternative_payload.get("status") != "VALID"
                ):
                    errors.append(f"alternative evidence is not VALID: {alternative}")
    return errors


def quality_contract_check(runtime: Any, current_stage: str) -> CheckResult:
    """Return the profile contract result for the current stage.

    ``adaptive`` intentionally returns PASS: it preserves compatibility for
    existing projects while leaving the scientific-depth contract available.
    Any explicit deeper profile is checked only for evidence belonging to the
    current workflow prefix, so future-stage work is never accepted early.
    """
    try:
        profile = selected_profile(runtime)
        skill_root = getattr(runtime, "skill_root", Path(__file__).resolve().parents[2])
        policy = load_quality_policy(skill_root)
        profile_definition = policy["profiles"][profile]
        if profile == "adaptive":
            return CheckResult(
                rule_id="QUALITY-PROFILE-adaptive",
                status="PASS",
                severity="MAJOR",
                reason="adaptive profile selected; no additional fixed-format quota is imposed",
            )
        required_by_stage = profile_definition.get("required_evidence_by_stage", {})
        core = set(profile_definition.get("core_evidence", []))
        by_type = _records(runtime)
        current_index = _stage_index(current_stage)
        errors: list[str] = []
        for stage, evidence_types in required_by_stage.items():
            if _stage_index(stage) > current_index:
                continue
            if not isinstance(evidence_types, list):
                raise IntegrityError(f"quality profile {profile} has invalid stage list: {stage}")
            for evidence_type in evidence_types:
                if (
                    evidence_type == "independent_review_provenance"
                    and not hasattr(runtime, "skill_root")
                ):
                    # Compatibility for policy-only legacy test doubles; a
                    # real project Runtime never takes this branch.
                    continue
                errors.extend(
                    _check_item(
                        by_type,
                        evidence_type,
                        str(stage),
                        profile,
                        runtime,
                        core=evidence_type in core,
                        current_stage=current_stage,
                    )
                )
        if errors:
            return CheckResult(
                rule_id=f"QUALITY-PROFILE-{profile}",
                status="FAIL",
                severity="MAJOR",
                reason=f"special-prize quality contract failed: {'; '.join(errors[:8])}",
                minimum_fix=[
                    "register the missing depth evidence in the declared stage",
                    "for conditional items, record a justified NOT_APPLICABLE decision and alternative evidence",
                ],
                rerun_scope=[f"P{i}" for i in range(current_index, 12)],
            )
        return CheckResult(
            rule_id=f"QUALITY-PROFILE-{profile}",
            status="PASS",
            severity="MAJOR",
            reason=f"quality profile {profile} has complete stage-scoped scientific-depth evidence",
        )
    except (ConfigError, IntegrityError) as error:
        return CheckResult(
            rule_id="QUALITY-PROFILE-INTEGRITY",
            status="ERROR",
            severity="CRITICAL",
            reason=f"quality profile policy error: {error}",
        )
    except Exception as error:
        # A damaged registry/workflow or a custom runtime adapter must fail
        # closed as a structured gate result.  Letting an ordinary runtime
        # exception escape would turn a quality failure into an unclassified
        # process crash and could hide the real integrity boundary.
        return CheckResult(
            rule_id="QUALITY-PROFILE-RUNTIME",
            status="ERROR",
            severity="CRITICAL",
            reason=(
                "quality profile runtime error: "
                f"{type(error).__name__}: {error}"
            ),
        )
