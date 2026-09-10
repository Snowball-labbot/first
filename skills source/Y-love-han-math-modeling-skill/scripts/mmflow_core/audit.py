from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from .bindings import (
    scan_unbound_numbers,
    scan_project_latex_sources,
    source_closure_matches,
    verify_project_binding_manifest,
    verify_binding_manifest,
    verify_result_source,
)
from .applicability import required_adapters, validate_adapter_coverage
from .canonical import (
    is_reparse_point,
    normalize_relative_posix,
    path_chain_has_reparse,
    resolve_regular_file_within,
    resolve_within,
    sha256_file,
)
from .compliance import evaluate_requirements, validate_requirements
from .privacy import scan_manifest_files
from .errors import (
    BlockedError,
    ConfigError,
    EvidenceInsufficientError,
    GateFailedError,
    IntegrityError,
)
from .gates import CheckResult
from .lineage import LineageGraph, invalidate_stage_downstream, stage_index
from .project import Runtime
from .quality import quality_contract_check
from .runner import ExecutionResult, ExecutionRunner


def _fail(message: str) -> EvidenceInsufficientError:
    """Business-level gate failure: the submitted evidence does not satisfy
    the stage requirements.  Classified FAIL, never ERROR."""
    return EvidenceInsufficientError(message)


def _load_quality_rubric(runtime: Runtime) -> dict[str, list[str]]:
    """Load the dimension -> allowed evidence types rubric from policy."""
    try:
        schemas = json.loads(
            (
                runtime.skill_root
                / "scripts/mmflow_core/policies/schemas-v1.json"
            ).read_text("utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IntegrityError("cannot load quality rubric policy") from error
    rubric = schemas.get("quality_rubric")
    if not isinstance(rubric, dict):
        raise IntegrityError("quality rubric policy is missing")
    return {
        str(dimension): [str(item) for item in allowed]
        for dimension, allowed in rubric.items()
        if isinstance(allowed, list)
    }


def _load_quality_dimensions(runtime: Runtime) -> dict[str, float]:
    """Load the eight quality dimensions from the versioned policy.

    The dimension set and maxima live in schemas-v1.json (single source of
    truth) so callers can introspect them via ``mmflow schema`` instead of
    reverse-engineering this checker.
    """
    try:
        schemas = json.loads(
            (
                runtime.skill_root
                / "scripts/mmflow_core/policies/schemas-v1.json"
            ).read_text("utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IntegrityError("cannot load quality dimension policy") from error
    dimensions = schemas.get("quality_dimensions")
    if not isinstance(dimensions, dict) or not dimensions:
        raise IntegrityError("quality dimension policy is missing")
    return {
        str(identifier): float(value)
        for identifier, value in dimensions.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def _rerun_scope_for(runtime: Runtime, stage: str) -> list[str]:
    """Downstream re-run scope: the failing stage and every later stage."""
    start = stage_index(stage)
    return [f"P{index}" for index in range(start, 12)]


FORBIDDEN_PACKAGE_PREFIXES = (
    ".mmflow/",
    "legacy/",
    "tests/",
    "docs/superpowers/",
    "internal-review/",
)

FINAL_DELIVERY_ARTIFACT_CLASSES = {"production", "external"}


def _casefold_delivery_path(relative: str) -> str:
    return relative.casefold()


def _manifest_artifact_map(runtime: Runtime) -> dict[str, dict[str, Any]]:
    """Index current VALID deliverable-capable artifacts by canonical path."""

    result: dict[str, dict[str, Any]] = {}
    for record in runtime.registry.iter_latest("artifact"):
        payload = record["payload"]
        if (
            payload.get("status") != "VALID"
            or payload.get("artifact_class") not in FINAL_DELIVERY_ARTIFACT_CLASSES
        ):
            continue
        relative = payload.get("relative_path")
        if not isinstance(relative, str):
            continue
        try:
            normalized = normalize_relative_posix(relative, field="artifact.relative_path")
        except IntegrityError:
            continue
        folded = _casefold_delivery_path(normalized)
        if folded in result and result[folded]["entity_id"] != record["entity_id"]:
            raise IntegrityError(f"multiple VALID artifacts collide by case: {normalized}")
        result[folded] = record
    return result


def _validate_manifest_items(
    runtime: Runtime,
    items: Any,
    *,
    require_artifact_ids: bool = True,
) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list) or not items:
        raise IntegrityError("delivery manifest must contain at least one file")
    artifacts = _manifest_artifact_map(runtime)
    expected: dict[str, dict[str, Any]] = {}
    folded_seen: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise IntegrityError("delivery manifest entries must be objects")
        relative = normalize_relative_posix(item.get("path"), field="delivery path")
        folded = _casefold_delivery_path(relative)
        if folded in folded_seen:
            raise IntegrityError(
                f"delivery manifest contains case-fold collision: {folded_seen[folded]} / {relative}"
            )
        folded_seen[folded] = relative
        if any(
            relative == prefix[:-1].casefold()
            or _casefold_delivery_path(relative).startswith(prefix.casefold())
            for prefix in FORBIDDEN_PACKAGE_PREFIXES
        ):
            raise IntegrityError(f"delivery manifest contains a forbidden path: {relative}")
        digest = item.get("sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
            raise IntegrityError(f"delivery manifest hash is invalid: {relative}")
        artifact_id = item.get("artifact_id")
        if require_artifact_ids and (
            not isinstance(artifact_id, str) or not artifact_id
        ):
            raise IntegrityError(f"delivery manifest lacks artifact_id: {relative}")
        record = artifacts.get(folded)
        if record is None:
            raise IntegrityError(f"delivery path has no current VALID artifact: {relative}")
        payload = record["payload"]
        if require_artifact_ids and artifact_id != record["entity_id"]:
            raise IntegrityError(f"delivery artifact binding mismatch: {relative}")
        if payload.get("sha256") != digest:
            raise IntegrityError(f"delivery artifact hash differs from manifest: {relative}")
        source = resolve_within(
            runtime.project_root,
            runtime.project_root / relative,
            must_exist=True,
        )
        if (
            not source.is_file()
            or is_reparse_point(source)
            or path_chain_has_reparse(source, runtime.project_root)
            or sha256_file(source) != digest
        ):
            raise IntegrityError(f"delivery artifact file is missing or changed: {relative}")
        expected[relative] = {
            "sha256": digest,
            "artifact_id": record["entity_id"],
        }
    return expected


def _evidence_payload(runtime: Runtime, evidence_type: str) -> dict[str, Any]:
    records = [
        record
        for record in runtime.registry.iter_latest("evidence")
        if record["payload"].get("status") == "VALID"
        and record["payload"].get("evidence_type") == evidence_type
    ]
    if len(records) != 1:
        raise _fail(
            f"expected one valid evidence record for {evidence_type}"
        )
    payload = records[0]["payload"]
    content = payload.get("content")
    if not isinstance(content, dict):
        raise _fail(f"evidence content is invalid: {evidence_type}")
    return payload


def _evidence(runtime: Runtime, evidence_type: str) -> dict[str, Any]:
    return _evidence_payload(runtime, evidence_type)["content"]


def _coverage_figure_payload(runtime: Runtime, record: dict[str, Any]) -> dict[str, Any]:
    """Return a planner view of a Registry figure with verified provenance.

    ``artifact_class`` is intentionally not duplicated in the Figure entity
    contract.  The image Artifact is the authoritative source of that fact;
    derive it only after reading the current Registry record.  This keeps the
    semantic coverage gate aligned with the same production gate used when a
    figure was registered and prevents a hand-written payload from promoting a
    demo/fixture image.
    """
    payload = dict(record.get("payload", {}))
    artifact_class: str | None = None
    artifact_id = payload.get("artifact_id")
    if isinstance(artifact_id, str):
        try:
            artifact = runtime.registry.latest("artifact", artifact_id)["payload"]
        except (IntegrityError, KeyError, TypeError):
            artifact = {}
        if artifact.get("status") == "VALID":
            artifact_class = artifact.get("artifact_class")
    payload["artifact_class"] = artifact_class

    # The planner's question-scoped Result contract is the primary check.  A
    # second local check makes the failure explicit even when a caller gives a
    # broad/global plan: a Q1 figure must not cite a Q2 Result.
    question_id = payload.get("question_id")
    source_results = payload.get("source_results")
    mismatches: list[str] = []
    if isinstance(question_id, str) and isinstance(source_results, list):
        for result_id in source_results:
            if not isinstance(result_id, str):
                mismatches.append(str(result_id))
                continue
            try:
                result = runtime.registry.latest("result", result_id)["payload"]
            except (IntegrityError, KeyError, TypeError):
                continue
            if result.get("question_id") != question_id:
                mismatches.append(result_id)
    if mismatches:
        payload["source_result_question_mismatch"] = sorted(set(mismatches))
    return payload


def _verify_competition_rule_snapshots(
    runtime: Runtime,
    rules_payload: dict[str, Any],
) -> None:
    rules = rules_payload["content"]
    competition = runtime.contract.get("competition")
    edition = runtime.contract.get("edition")
    if (
        not isinstance(competition, str)
        or not isinstance(edition, str)
        or rules.get("competition") != competition
        or rules.get("edition") != edition
    ):
        raise IntegrityError("rule snapshot competition or edition differs from project contract")

    official_sources = rules.get("official_sources")
    snapshots = rules.get("rule_snapshots")
    if not isinstance(official_sources, list) or not official_sources:
        raise IntegrityError("rule snapshot has no official source record")
    if not isinstance(snapshots, list) or not snapshots:
        raise IntegrityError("rule snapshot list is empty")
    if not all(isinstance(item, dict) for item in official_sources + snapshots):
        raise IntegrityError("rule snapshot and official-source entries must be objects")

    supports = rules_payload.get("supports")
    if not isinstance(supports, list):
        raise IntegrityError("rule snapshot evidence supports are invalid")
    supported_ids = set(supports)
    seen_pairs: set[tuple[str, str]] = set()
    for snapshot in snapshots:
        artifact_id = snapshot.get("artifact_id")
        citation_id = snapshot.get("citation_id")
        digest = snapshot.get("sha256")
        pair = (str(artifact_id), str(citation_id))
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or not isinstance(citation_id, str)
            or not citation_id
            or not re.fullmatch(r"[0-9a-f]{64}", str(digest))
        ):
            raise IntegrityError("rule snapshot lacks a valid artifact, citation, or SHA-256")
        if pair in seen_pairs:
            raise IntegrityError("rule snapshot artifact/citation pair is duplicated")
        seen_pairs.add(pair)
        if (
            snapshot.get("competition") != competition
            or snapshot.get("edition") != edition
        ):
            raise IntegrityError("rule snapshot competition or edition does not match current run")
        if artifact_id not in supported_ids or citation_id not in supported_ids:
            raise IntegrityError("rule snapshot evidence does not support its artifact and citation")

        artifact = _valid(runtime, "artifact", artifact_id)
        if (
            artifact.get("artifact_type") != "official_rule_snapshot"
            or artifact.get("artifact_class") not in {"external", "production"}
            or artifact.get("sha256") != digest
        ):
            raise IntegrityError("rule snapshot artifact binding is invalid")
        snapshot_path = resolve_regular_file_within(
            runtime.project_root,
            runtime.project_root / str(artifact.get("relative_path", "")),
        )
        if sha256_file(snapshot_path) != digest:
            raise IntegrityError("rule snapshot file has changed since registration")

        citation = _valid(runtime, "citation", citation_id)
        if (
            citation.get("source_role") != "official_rule"
            or citation.get("verification_status") != "verified"
        ):
            raise IntegrityError("rule snapshot citation is not a verified official rule")
        matching_sources = [
            source
            for source in official_sources
            if source.get("artifact_id") == artifact_id
            and source.get("citation_id") == citation_id
        ]
        if len(matching_sources) != 1:
            raise IntegrityError("rule snapshot has no unique matching official-source record")
        source = matching_sources[0]
        if (
            source.get("source_url") != citation.get("source_url")
            or source.get("retrieved_at") != citation.get("verified_at")
            or not isinstance(source.get("version"), str)
            or not source["version"].strip()
        ):
            raise IntegrityError("rule snapshot official-source metadata is inconsistent")

    referenced_pairs = {
        (str(source.get("artifact_id")), str(source.get("citation_id")))
        for source in official_sources
    }
    if referenced_pairs != seen_pairs:
        raise IntegrityError("official-source records and rule snapshots are not one-to-one")


def _valid(runtime: Runtime, kind: str, entity_id: str) -> dict[str, Any]:
    payload = runtime.registry.latest(kind, entity_id)["payload"]
    if payload.get("status") != "VALID":
        raise _fail(f"entity is not VALID: {entity_id}")
    return payload


def semantic_stage_check(runtime: Runtime, stage: str) -> CheckResult:
    try:
        if stage_index(stage) >= stage_index("P4") and stage_index(stage) <= stage_index("P10"):
            quality_result = quality_contract_check(runtime, stage)
            if quality_result.status != "PASS":
                return quality_result
        if stage == "P0":
            capabilities = _evidence(runtime, "capability_report")
            rules_payload = _evidence_payload(runtime, "competition_rules")
            rules = rules_payload["content"]
            lock = _evidence(runtime, "policy_lock")
            if not isinstance(capabilities.get("capabilities"), dict):
                raise _fail("capability report is incomplete")
            if rules["verification_status"] != "verified" or not rules["official_sources"]:
                raise _fail("current official rules are not verified")
            _verify_competition_rule_snapshots(runtime, rules_payload)
            if lock["policy_sha256"] != runtime.policy_lock["policy_sha256"]:
                raise _fail("policy-lock evidence differs from active policy")
            if lock["files"] != runtime.policy_lock["files"]:
                raise _fail("policy-lock evidence file set differs from active policy")
            requirement_errors = validate_requirements(rules.get("requirements"))
            if requirement_errors:
                raise _fail(
                    "competition rule requirements are not structured: "
                    + "; ".join(requirement_errors[:5])
                )
        elif stage == "P1":
            inventory = _evidence(runtime, "input_inventory")
            selection = _evidence(runtime, "selection_record")
            if inventory["critical_missing"]:
                raise _fail("critical input remains missing")
            if not inventory["files"]:
                raise _fail("input inventory is empty")
            seen_inventory: set[str] = set()
            for item in inventory["files"]:
                artifact_id = item.get("artifact_id")
                if (
                    not isinstance(artifact_id, str)
                    or artifact_id in seen_inventory
                ):
                    raise _fail("input inventory has duplicate or invalid artifact ids")
                seen_inventory.add(artifact_id)
                artifact = _valid(runtime, "artifact", artifact_id)
                if item.get("read_status") != "complete" or not re.fullmatch(
                    r"[0-9a-f]{64}", str(item.get("sha256", ""))
                ):
                    raise _fail("input inventory contains unread or unhashed file")
                if item.get("sha256") != artifact["sha256"]:
                    raise _fail(
                        f"input inventory hash differs from registered artifact: {artifact_id}"
                    )
            if selection["applicable"]:
                if (
                    not isinstance(selection.get("candidates"), list)
                    or not selection["candidates"]
                    or selection["selected"] not in selection["candidates"]
                ):
                    raise _fail(
                        "selection is applicable but has no valid candidates or selection"
                    )
            elif selection.get("candidates"):
                raise _fail("not-applicable selection must not declare candidates")
        elif stage == "P2":
            matrix = _evidence(runtime, "requirement_matrix")
            contract = _evidence(runtime, "problem_contract")
            if not matrix["requirements"] or not contract["problems"]:
                raise _fail("formalization is empty")
            requirement_ids = [row.get("requirement_id") for row in matrix["requirements"]]
            if any(not isinstance(item, str) or not item for item in requirement_ids):
                raise _fail("requirement rows must carry requirement ids")
            if len(requirement_ids) != len(set(requirement_ids)):
                raise _fail("requirement matrix has duplicate requirement ids")
            for row in matrix["requirements"]:
                if not all(
                    row.get(key)
                    for key in ("requirement_id", "source_anchor", "response_target")
                ):
                    raise _fail("requirement row lacks source or response target")
            problem_ids: list[str] = []
            for problem in contract["problems"]:
                if not all(
                    key in problem
                    for key in (
                        "problem_id",
                        "traits",
                        "claim_types",
                        "model_families",
                        "properties",
                    )
                ):
                    raise _fail("problem contract is incomplete")
                problem_id = problem.get("problem_id")
                if not isinstance(problem_id, str) or problem_id in problem_ids:
                    raise _fail("problem contract has duplicate or invalid problem ids")
                problem_ids.append(problem_id)
                if not problem.get("claim_types"):
                    raise _fail(f"problem {problem_id} declares no claim types")
                try:
                    required_adapters(problem)
                except ConfigError as error:
                    raise _fail(f"problem {problem_id} uses unknown traits or types: {error}") from error
        elif stage == "P3":
            lineage = _evidence(runtime, "data_lineage")
            quality = _evidence(runtime, "data_quality_report")
            leakage = _evidence(runtime, "leakage_audit")
            literature = _evidence(runtime, "literature_registry")
            if not quality["datasets"]:
                raise _fail("data quality report has no dataset")
            dataset_ids: list[str] = []
            for dataset in quality["datasets"]:
                dataset_id = dataset.get("artifact_id")
                if not isinstance(dataset_id, str) or dataset_id in dataset_ids:
                    raise _fail("data quality report has duplicate dataset ids")
                dataset_ids.append(dataset_id)
                _valid(runtime, "artifact", dataset_id)
            for source in lineage["sources"]:
                source_id = source.get("artifact_id")
                if not isinstance(source_id, str):
                    raise _fail("data lineage source lacks artifact binding")
                _valid(runtime, "artifact", source_id)
            split_ids = lineage.get("splits", [])
            if not isinstance(split_ids, list):
                raise _fail("data lineage splits must be a list")
            for split_id in split_ids:
                record = runtime.registry.find_entity(split_id)
                if (
                    record["entity_kind"] != "split"
                    or record["payload"].get("status") != "VALID"
                ):
                    raise _fail(f"data lineage split is not a current valid split: {split_id}")
            if leakage["status"] != "PASS" or not leakage["checks"]:
                raise _fail("data leakage audit did not pass or has no checks")
            if literature["unresolved"]:
                raise _fail("unresolved literature remains")
            literature_ids = literature.get("citation_ids", [])
            if not isinstance(literature_ids, list):
                raise _fail("literature citation_ids must be a list")
            if len(literature_ids) != len(set(literature_ids)):
                raise _fail("literature citation ids are duplicated")
            for citation_id in literature_ids:
                citation = _valid(runtime, "citation", citation_id)
                if citation.get("verification_status") not in {"verified", "corrected"}:
                    raise _fail(
                        f"literature citation is not metadata-verified: {citation_id}"
                    )
                if citation.get("access_level") == "deleted":
                    raise _fail(f"literature citation points to a deleted source: {citation_id}")
        elif stage == "P4":
            baseline = _evidence(runtime, "baseline_protocol")
            candidates = _evidence(runtime, "model_candidates")
            validation = _evidence(runtime, "validation_protocol")
            frozen = _evidence(runtime, "frozen_analysis_plan")
            if (
                not baseline["baselines"]
                or not candidates["candidates"]
                or not validation["adapters"]
            ):
                raise _fail("baseline, candidates, or validation protocol is empty")
            if frozen["viewed_final_test"] is not False or not frozen["primary_metrics"]:
                raise _fail("analysis plan was not frozen before final-test inspection")
            if not validation["comparison_policies"]:
                raise _fail("reproduction comparison policies are missing")
            frozen_at = frozen.get("frozen_at")
            try:
                from datetime import datetime

                parsed_frozen = datetime.fromisoformat(str(frozen_at))
            except (TypeError, ValueError) as error:
                raise _fail("frozen analysis plan has no parseable frozen_at") from error
            if parsed_frozen.tzinfo is None:
                raise _fail("frozen_at must be timezone-aware")
            frozen_split_ids = frozen.get("split_ids", [])
            if not isinstance(frozen_split_ids, list):
                raise _fail("frozen analysis plan split_ids must be a list")
            for split_id in frozen_split_ids:
                record = runtime.registry.find_entity(split_id)
                if (
                    record["entity_kind"] != "split"
                    or record["payload"].get("status") != "VALID"
                ):
                    raise _fail(
                        f"frozen analysis plan split is not a current valid split: {split_id}"
                    )
            adapter_ids = [adapter for adapter in validation["adapters"]]
            if len(adapter_ids) != len(set(adapter_ids)):
                raise _fail("validation protocol adapters are duplicated")
        elif stage == "P5":
            executions = _evidence(runtime, "production_execution")
            results = _evidence(runtime, "structured_results")
            if not executions["execution_ids"] or not results["result_ids"]:
                raise _fail("production executions or structured results are empty")
            for execution_id in executions["execution_ids"]:
                execution = _valid(runtime, "execution", execution_id)
                if (
                    execution["artifact_class"] != "production"
                    or execution["exit_code"] != 0
                ):
                    raise _fail("non-production execution cited as production evidence")
            # The frozen analysis plan must predate every final-test execution:
            # ledger ordering, not self-report, proves the freeze happened first.
            frozen_records = [
                record
                for record in runtime.registry.iter_latest("evidence")
                if record["payload"].get("status") == "VALID"
                and record["payload"].get("evidence_type") == "frozen_analysis_plan"
            ]
            if len(frozen_records) != 1:
                raise _fail("frozen analysis plan evidence is missing or duplicated")
            freeze_sequence = int(frozen_records[0].get("created_ledger_sequence", 0))
            for execution_id in executions["execution_ids"]:
                record = runtime.registry.latest("execution", execution_id)
                if int(record.get("created_ledger_sequence", 0)) <= freeze_sequence:
                    raise _fail(
                        f"execution {execution_id} predates the frozen analysis plan"
                    )
            for result_id in results["result_ids"]:
                verify_result_source(runtime.project_root, runtime.registry, result_id)
        elif stage == "P6":
            reports = _evidence(runtime, "validation_adapter_report")
            degenerate = _evidence(runtime, "degenerate_test")
            counter = _evidence(runtime, "counterevidence_report")
            contracts = _evidence(runtime, "problem_contract")
            if degenerate["status"] != "PASS" or counter["status"] != "PASS":
                raise _fail("degenerate or counterevidence testing failed")
            report_by_problem: dict[str, dict[str, Any]] = {}
            for report in reports["reports"]:
                problem_id = report.get("problem_id")
                if (
                    not isinstance(problem_id, str)
                    or problem_id in report_by_problem
                    or not isinstance(report.get("completed"), dict)
                    or not isinstance(report.get("waivers"), dict)
                ):
                    raise _fail(
                        "validation adapter report has missing or duplicate problem coverage"
                    )
                report_by_problem[problem_id] = report
            problems = contracts.get("problems")
            if not isinstance(problems, list) or not problems:
                raise _fail("problem contract is empty at P6")
            for contract in problems:
                problem_id = contract.get("problem_id")
                report = report_by_problem.get(problem_id)
                if report is None:
                    raise _fail(f"missing validation report for {problem_id}")
                try:
                    coverage = validate_adapter_coverage(
                        contract,
                        report["completed"],
                        report["waivers"],
                        lambda entity_id: (
                            runtime.registry.find_entity(entity_id)["payload"].get("status")
                        == "VALID"
                    ),
                )
                except ConfigError as error:
                    raise _fail(
                        f"problem contract is invalid for {problem_id}: {error}"
                    ) from error
                if coverage["status"] != "PASS":
                    raise _fail(
                        f"validation adapter coverage failed for {problem_id}: "
                        + str(coverage["missing_or_invalid"])
                    )
            if set(report_by_problem) != {
                contract.get("problem_id") for contract in problems
            }:
                raise _fail("validation reports contain unknown problem IDs")
            for claim_id in counter["unsupported_claims"]:
                claim = runtime.registry.latest("claim", claim_id)["payload"]
                if claim.get("strength") in {"confirmed", "supported"}:
                    raise _fail("unsupported claim remains promoted")
        elif stage == "P7":
            response = _evidence(runtime, "response_matrix")
            claims = _evidence(runtime, "claim_registry")
            if not response["rows"] or not claims["claim_ids"]:
                raise _fail("response or claim registry evidence is empty")
            for row in response["rows"]:
                if (
                    not row.get("requirement_id")
                    or not row.get("claim_ids")
                    or not row.get("manuscript_target")
                ):
                    raise _fail("a problem requirement has no answer mapping")
                for claim_id in row["claim_ids"]:
                    _valid(runtime, "claim", claim_id)
            for claim_id in claims["claim_ids"]:
                _valid(runtime, "claim", claim_id)
            # M-P7a: cross-check the response rows against the requirement
            # matrix registered at P2.  Without this join a whole question
            # requirement could stay unanswered while P7 still passes; the
            # `unanswered_requirement` redline gets its programmatic
            # enforcement point here.
            required_ids: set[str] = set()
            requirement_records = [
                record
                for record in runtime.registry.iter_latest("evidence")
                if record["payload"].get("status") == "VALID"
                and record["payload"].get("evidence_type") == "requirement_matrix"
            ]
            if requirement_records:
                newest = max(
                    requirement_records,
                    key=lambda record: int(record.get("created_ledger_sequence", 0)),
                )
                matrix_items = (
                    newest["payload"].get("content", {}).get("requirements", [])
                )
                for item in matrix_items:
                    if isinstance(item, dict) and item.get("requirement_id"):
                        required_ids.add(str(item["requirement_id"]))
            answered_ids = {
                str(row.get("requirement_id"))
                for row in response["rows"]
                if row.get("requirement_id")
            }
            missing = sorted(required_ids - answered_ids)
            if missing:
                raise _fail(
                    "unanswered_requirement: requirements registered at P2 "
                    + "have no answer mapping in the response matrix: "
                    + ", ".join(missing)
                )
            # M-P7a-reverse: rows answering requirements that were never
            # registered at P2 are ghost mappings - they inflate coverage or
            # smuggle in unformalized scope.  Only enforced when the matrix
            # actually declares requirements, so legacy empty registries keep
            # working unchanged.
            if required_ids:
                unknown = sorted(answered_ids - required_ids)
                if unknown:
                    raise _fail(
                        "ghost_requirement: response_matrix answers "
                        "requirements never registered at P2: "
                        + ", ".join(unknown)
                    )
            # M-P7b (v3.0.4 widened): EVERY currently-VALID claim in the run
            # must be listed in the claim_registry evidence - not just claims
            # created inside the P7 epoch.  Earlier-epoch claims are rare but
            # legal (stage-binding windows), and leaving them out would let
            # conclusions bypass the response matrix.  STALE/INVALID versions
            # are ignored by the status filter below.
            listed_claims = {str(cid) for cid in claims["claim_ids"]}
            unlisted = sorted(
                record["entity_id"]
                for record in runtime.registry.iter_latest("claim")
                if record["payload"].get("status") == "VALID"
                and record["entity_id"] not in listed_claims
            )
            if unlisted:
                raise _fail(
                    "claims registered in P7 are missing from the claim "
                    "registry evidence: " + ", ".join(unlisted)
                )
        elif stage == "P8":
            manuscript = _evidence(runtime, "manuscript_source")
            figures = _evidence(runtime, "figure_registry")
            citations = _evidence(runtime, "citation_audit")
            # Projects that opted into the question-adaptive planner receive
            # a semantic coverage gate.  Legacy fixtures without a plan keep
            # the historical publication checks, so this is strictly
            # conditional and does not invent required figures.
            coverage_plan_path = runtime.project_root / ".mmflow" / "figure-coverage-plan.json"
            if coverage_plan_path.is_file():
                try:
                    coverage_plan = json.loads(coverage_plan_path.read_text("utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as error:
                    raise _fail("figure coverage plan is not valid JSON") from error
                from .figure_plan import verify_figure_coverage

                figure_payloads = [
                    _coverage_figure_payload(runtime, record)
                    for record in runtime.registry.iter_latest("figure")
                    if record["payload"].get("status") == "VALID"
                ]
                # Registry records are authoritative; enrich only with the
                # artifact class already proven by the Registry gate.
                coverage = verify_figure_coverage(coverage_plan, figure_payloads)
                if coverage["status"] != "PASS":
                    raise _fail(
                        "figure coverage plan has missing required roles: "
                        + json.dumps(coverage.get("missing", []), ensure_ascii=False)
                    )
            source = _valid(runtime, "artifact", manuscript["source_artifact_id"])
            rendered = _valid(runtime, "artifact", manuscript["rendered_artifact_id"])
            binding_manifest = _valid(
                runtime, "artifact", manuscript["binding_manifest_artifact_id"]
            )
            publication_execution_id = manuscript.get("publication_execution_id")
            if not isinstance(publication_execution_id, str):
                raise _fail(
                    "manuscript evidence lacks a publication_execution_id for "
                    "the controlled compile"
                )
            compile_dependencies = manuscript.get("compile_dependencies")
            if not isinstance(compile_dependencies, list):
                raise _fail(
                    "manuscript evidence lacks the complete compile_dependencies list"
                )
            for entry in compile_dependencies:
                if not isinstance(entry, dict):
                    raise _fail("compile dependency entry must be an object")
                artifact_id = entry.get("artifact_id")
                role = entry.get("role")
                if (
                    not isinstance(artifact_id, str)
                    or role
                    not in {
                        "bibliography",
                        "style",
                        "class",
                        "image",
                        "font",
                        "other",
                    }
                ):
                    raise _fail("compile dependency entry is malformed")
                artifact = _valid(runtime, "artifact", artifact_id)
                if artifact.get("artifact_class") == "production":
                    if artifact.get("execution_id") != publication_execution_id:
                        raise _fail(
                            f"production compile dependency {artifact_id} is not "
                            "an output of the declared publication execution"
                        )
                elif artifact.get("artifact_class") != "external":
                    raise _fail(
                        f"compile dependency {artifact_id} must be a production "
                        "output or an immutable external dependency"
                    )
            publication_execution = _valid(
                runtime, "execution", publication_execution_id
            )
            if (
                publication_execution.get("artifact_class") != "production"
                or publication_execution.get("exit_code") != 0
            ):
                raise _fail(
                    "publication execution is not a passing production execution"
                )
            if (
                rendered.get("artifact_class") != "production"
                or binding_manifest.get("artifact_class") != "production"
            ):
                raise _fail(
                    "rendered manuscript and binding manifest must be production artifacts"
                )
            if (
                rendered.get("execution_id") != publication_execution_id
                or binding_manifest.get("execution_id") != publication_execution_id
            ):
                raise _fail(
                    "rendered manuscript, binding manifest and the declared "
                    "publication execution must be one controlled compile"
                )
            if manuscript["binding_count"] <= 0 or manuscript["unbound_number_count"] != 0:
                raise _fail("manuscript has no bindings or unbound scientific numbers remain")
            source_path = resolve_within(
                runtime.project_root,
                runtime.project_root / source["relative_path"],
                must_exist=True,
            )
            rendered_path = resolve_within(
                runtime.project_root,
                runtime.project_root / rendered["relative_path"],
                must_exist=True,
            )
            manifest_path = resolve_within(
                runtime.project_root,
                runtime.project_root / binding_manifest["relative_path"],
                must_exist=True,
            )
            try:
                manifest_value = json.loads(manifest_path.read_text("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise _fail("cannot parse production binding manifest") from error
            source_text = source_path.read_text("utf-8")
            rendered_text = rendered_path.read_text("utf-8")
            if manifest_value.get("binding_manifest_version") != 2:
                raise _fail(
                    "final publication requires binding manifest v2; "
                    "legacy v1 manifests are not accepted for v2 publication"
                )
            try:
                verify_project_binding_manifest(
                    runtime.project_root,
                    source_path,
                    manifest_value,
                    runtime.registry,
                )
            except IntegrityError as error:
                # A rendered-then-replaced source is a publication closure
                # failure the team must fix by re-registering, not an internal
                # state corruption; classify it as a business FAIL.
                raise _fail(f"publication closure mismatch: {error}") from error
            if manifest_value.get("binding_count") != manuscript["binding_count"]:
                raise _fail("P8 evidence binding count differs from manifest")
            closure = scan_project_latex_sources(runtime.project_root, source_path)
            if len(closure["hits"]) != manuscript["unbound_number_count"]:
                raise _fail("P8 evidence unbound-number count differs from source")
            declared_sources = manuscript.get("source_closure")
            if not isinstance(declared_sources, list) or not declared_sources:
                raise _fail("P8 evidence lacks a complete LaTeX source closure")
            if not source_closure_matches(closure["sources"], declared_sources):
                raise _fail("P8 source closure differs from current files")
            for source_item in declared_sources:
                artifact_id = source_item.get("artifact_id")
                if not isinstance(artifact_id, str):
                    raise _fail("P8 source closure item lacks artifact binding")
                artifact = _valid(runtime, "artifact", artifact_id)
                if (
                    artifact.get("relative_path") != source_item.get("path")
                    or artifact.get("sha256") != source_item.get("sha256")
                ):
                    raise _fail("P8 source closure artifact binding is invalid")
                if artifact.get("artifact_class") == "production":
                    if artifact.get("execution_id") != publication_execution_id:
                        raise _fail(
                            f"production closure source {artifact_id} is not an "
                            "output of the declared publication execution"
                        )
                elif artifact.get("artifact_class") != "external":
                    raise _fail(
                        f"closure source {artifact_id} must be a production "
                        "output or a registered immutable external dependency"
                    )
            for figure_id in figures["figure_ids"]:
                _valid(runtime, "figure", figure_id)
            if citations["unresolved"]:
                raise _fail("citation audit has unresolved records")
            for citation_id in citations["citation_ids"]:
                _valid(runtime, "citation", citation_id)
            # M13: bidirectional use coverage between manuscript and Registry.
            from .bindings import _project_latex_closure as _read_closure

            closure_records = _read_closure(runtime.project_root, source_path)["sources"]
            manuscript_text = "\n".join(record["content"] for record in closure_records)
            cited_ids: set[str] = set()
            for match in re.finditer(r"\\cite(?:\[[^\]]*\])?\{([^{}]+)\}", manuscript_text):
                for token in match.group(1).split(","):
                    token = token.strip()
                    if token:
                        cited_ids.add(token)
            for citation_id in citations["citation_ids"]:
                if citation_id not in cited_ids:
                    raise _fail(
                        f"registered citation is never cited in the manuscript: {citation_id}"
                    )
            for citation_id in cited_ids:
                _valid(runtime, "citation", citation_id)
            included_images: set[str] = set()
            for match in re.finditer(
                r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}", manuscript_text
            ):
                included_images.add(Path(match.group(1).strip()).name)
            figure_image_names: dict[str, str] = {}
            for figure_id in figures["figure_ids"]:
                figure = _valid(runtime, "figure", figure_id)
                image = _valid(runtime, "artifact", figure["artifact_id"])
                figure_image_names[Path(image["relative_path"]).name] = figure_id
            for image_name in included_images:
                if image_name not in figure_image_names:
                    raise _fail(
                        f"manuscript includes an unregistered image: {image_name}"
                    )
            # F2: figure_image_names maps image basename -> figure id;
            # unpack accordingly so the inclusion test compares basenames.
            for image_name, figure_id in figure_image_names.items():
                if image_name not in included_images:
                    raise _fail(
                        f"registered figure is not included in the manuscript: {figure_id}"
                    )
        elif stage == "P9":
            reproduction = _evidence(runtime, "reproduction_report")
            production = _evidence(runtime, "production_execution")
            validation = _evidence(runtime, "validation_protocol")
            drift_policy = validation.get("environment_drift_policy")
            if (
                not isinstance(drift_policy, dict)
                or not isinstance(drift_policy.get("allowed_differences"), list)
                or not all(
                    isinstance(item, str) for item in drift_policy["allowed_differences"]
                )
            ):
                raise _fail(
                    "validation protocol lacks a frozen environment_drift_policy "
                    "with allowed_differences"
                )
            allowed_drift = set(drift_policy["allowed_differences"])
            reports_by_original: dict[str, dict[str, Any]] = {}
            for report in reproduction["reports"]:
                original_id = report.get("original_execution_id")
                reproduction_id = report.get("reproduction_execution_id")
                checks = report.get("checks")
                if (
                    report.get("outcome") != "PASS"
                    or not isinstance(original_id, str)
                    or original_id in reports_by_original
                    or not isinstance(reproduction_id, str)
                    or not isinstance(checks, list)
                    or not checks
                    or any(check.get("status") != "PASS" for check in checks)
                ):
                    raise _fail("reproduction report is incomplete or not passing")
                original = _valid(runtime, "execution", original_id)
                reproduced = _valid(runtime, "execution", reproduction_id)
                if (
                    original.get("artifact_class") != "production"
                    or reproduced.get("artifact_class") != "production"
                    or reproduced.get("stage") != "P9"
                    or reproduced.get("role") != f"reproduce:{original.get('role')}"
                    or reproduced.get("question") != original.get("question")
                    or reproduced.get("source_snapshots") != original.get("source_snapshots")
                    or reproduced.get("source_artifact_ids")
                    != original.get("source_artifact_ids")
                    or reproduced.get("expected_outputs")
                    != original.get("expected_outputs")
                    or reproduced.get("comparison_policies")
                    != original.get("comparison_policies")
                    or reproduced.get("dataset_split_ids")
                    != original.get("dataset_split_ids")
                    or reproduced.get("random_protocol")
                    != original.get("random_protocol")
                    or reproduced.get("timeout_seconds")
                    != original.get("timeout_seconds")
                ):
                    raise _fail(
                        "reproduction execution does not attest the original contract"
                    )
                if {check.get("logical_path") for check in checks} != set(
                    original.get("expected_outputs", [])
                ):
                    raise _fail("reproduction checks do not cover every output")
                reproduced_record = runtime.registry.latest(
                    "execution", reproduction_id
                )
                reproduced_artifacts = [
                    record
                    for record in runtime.registry.iter_latest("artifact")
                    if record["payload"].get("execution_id") == reproduction_id
                ]
                recomputed = ExecutionRunner(
                    runtime.project_root,
                    runtime.ledger,
                    runtime.registry,
                    runtime.run_id,
                ).compare_reproduction(
                    original_id,
                    ExecutionResult(
                        execution=reproduced_record,
                        artifacts=reproduced_artifacts,
                    ),
                )
                if recomputed != report:
                    raise _fail(
                        "registered reproduction report differs from recomputed comparison"
                    )
                conditions = report.get("conditions") or {}
                for field, condition in conditions.items():
                    if (
                        isinstance(condition, dict)
                        and condition.get("status") == "DIFF"
                        and field not in allowed_drift
                    ):
                        raise _fail(
                            f"environment drift in {field} is not allowed by the "
                            "frozen drift policy"
                        )
                reports_by_original[original_id] = report
            expected_originals = set(production["execution_ids"])
            if not expected_originals or set(reports_by_original) != expected_originals:
                raise _fail("isolated reproduction did not pass")
        elif stage == "P10":
            findings = _evidence(runtime, "review_findings")
            compliance = _evidence(runtime, "compliance_report")
            quality = _evidence(runtime, "quality_assessment")
            required_roles = {
                "competition_judge",
                "mathematics_numerics",
                "data_statistics",
                "reproducibility",
                "paper_compliance",
            }
            roles = findings.get("roles")
            if not isinstance(roles, list):
                raise _fail("review role records are missing")
            roles_by_name: dict[str, dict[str, Any]] = {}
            report_by_role: dict[str, dict[str, Any]] = {}
            last_p8_gate_sequence = max(
                (
                    int(event["sequence"])
                    for event in runtime.ledger.read_events()
                    if event.get("event_type") == "GATE_RECORDED"
                    and event.get("stage") == "P8"
                ),
                default=0,
            )
            for role in roles:
                name = role.get("role") if isinstance(role, dict) else None
                evidence_ids = role.get("evidence_ids") if isinstance(role, dict) else None
                if (
                    name not in required_roles
                    or name in roles_by_name
                    or role.get("status") != "COMPLETE"
                    or not isinstance(evidence_ids, list)
                    or not evidence_ids
                ):
                    raise _fail("five-role review record is incomplete")
                role_reports = [
                    record
                    for record in runtime.registry.iter_latest("evidence")
                    if record["entity_id"] in evidence_ids
                    and record["payload"].get("status") == "VALID"
                    and record["payload"].get("evidence_type") == "review_report"
                ]
                if len(role_reports) != 1:
                    raise _fail(
                        f"role {name} must be backed by exactly one review_report evidence"
                    )
                report_record = role_reports[0]
                report = report_record["payload"].get("content")
                if not isinstance(report, dict):
                    raise _fail(f"role {name} review report content is invalid")
                if report.get("role") != name:
                    raise _fail(
                        f"role {name} review report names a different role: {report.get('role')}"
                    )
                scope = report.get("scope")
                checks = report.get("checks")
                finding_ids = report.get("finding_ids")
                reviewer_mode = report.get("reviewer_mode")
                if (
                    not isinstance(scope, list)
                    or not scope
                    or not isinstance(checks, list)
                    or not checks
                    or not isinstance(finding_ids, list)
                    or reviewer_mode
                    not in {
                        "same_agent_roleplay",
                        "independent_agent",
                        "external_reviewer",
                    }
                ):
                    raise _fail(f"role {name} review report is incomplete")
                if int(report_record.get("created_ledger_sequence", 0)) <= last_p8_gate_sequence:
                    raise _fail(
                        f"role {name} review report was created before the reviewed manuscript"
                    )
                for finding_id in finding_ids:
                    _valid(runtime, "finding", finding_id)
                if set(finding_ids) != set(role.get("finding_ids", [])):
                    raise _fail(f"role {name} finding IDs differ from its report")
                report_by_role[name] = report
                roles_by_name[name] = role
            if set(roles_by_name) != required_roles:
                raise _fail("all five review roles must be complete")
            if len(report_by_role) != len(required_roles):
                raise _fail("one review report may not impersonate multiple roles")
            declared_independence = findings.get("independent_review")
            any_limited = any(
                report.get("reviewer_mode") == "same_agent_roleplay"
                for report in report_by_role.values()
            )
            if declared_independence == "independent" and any_limited:
                raise _fail(
                    "review independence is claimed independent but a role "
                    "used same-agent roleplay"
                )
            if declared_independence == "limited" and not any_limited:
                raise _fail(
                    "review independence is limited but every report claims "
                    "an independent reviewer"
                )
            if quality.get("review_independence") != declared_independence:
                raise _fail(
                    "quality assessment review independence differs from review evidence"
                )
            latest_findings = [
                record["payload"]
                for record in runtime.registry.iter_latest("finding")
                if record["payload"].get("status") == "VALID"
            ]
            if set(findings["finding_ids"]) != {
                item["finding_id"] for item in latest_findings
            }:
                raise _fail("review evidence omits or invents finding IDs")
            actual_open = {
                severity: sum(
                    1
                    for item in latest_findings
                    if item.get("severity") == severity
                    and item.get("finding_status") == "OPEN"
                )
                for severity in ("CRITICAL", "MAJOR", "MODERATE", "MINOR")
            }
            if findings["open_by_severity"] != actual_open:
                raise _fail("reported open findings differ from Registry")
            if actual_open["CRITICAL"] or actual_open["MAJOR"]:
                raise _fail("critical or major review findings remain open")
            if compliance["status"] != "PASS" or not compliance[
                "official_rule_citations"
            ]:
                raise _fail("competition compliance did not pass")
            for citation_id in compliance["official_rule_citations"]:
                citation = _valid(runtime, "citation", citation_id)
                if citation.get("source_role") != "official_rule":
                    raise _fail("compliance cites a non-official source")
            rules_payload = _evidence_payload(runtime, "competition_rules")
            registered_checks = compliance.get("requirement_checks")
            recomputed_checks = evaluate_requirements(
                runtime, rules_payload["content"].get("requirements")
            )
            if registered_checks != recomputed_checks:
                raise _fail(
                    "registered compliance requirement checks differ from "
                    "the rule-driven engine"
                )
            if any(check.get("status") != "PASS" for check in recomputed_checks):
                raise _fail("a structured competition requirement is not satisfied")
            expected_dimensions = _load_quality_dimensions(runtime)
            if not isinstance(expected_dimensions, dict):  # pragma: no cover
                raise _fail("quality dimension policy is invalid")
            dimensions = quality.get("dimensions")
            if not isinstance(dimensions, list):
                raise _fail("quality dimensions are missing")
            by_dimension: dict[str, dict[str, Any]] = {}
            for dimension in dimensions:
                identifier = dimension.get("id") if isinstance(dimension, dict) else None
                if identifier not in expected_dimensions or identifier in by_dimension:
                    raise _fail("quality dimension set is invalid")
                if float(dimension.get("maximum")) != expected_dimensions[identifier]:
                    raise _fail("quality dimension maximum differs from policy")
                earned = float(dimension.get("earned"))
                if earned < 0 or earned > expected_dimensions[identifier]:
                    raise _fail("quality dimension earned score is invalid")
                by_dimension[identifier] = dimension
            if set(by_dimension) != set(expected_dimensions):
                raise _fail("all eight quality dimensions are required")
            computed_total = sum(float(item["earned"]) for item in dimensions)
            if float(quality["total"]) != computed_total:
                raise _fail("quality total differs from dimension sum")
            if computed_total < 90 or not quality["contribution_claim_ids"]:
                raise _fail("quality threshold or contribution evidence not met")
            rubric = _load_quality_rubric(runtime)
            claimed_by_evidence: dict[str, str] = {}
            for dimension in dimensions:
                if not dimension.get("evidence_ids"):
                    raise _fail(
                        f"quality dimension has no evidence: {dimension.get('id')}"
                    )
                ratio = float(dimension["earned"]) / float(dimension["maximum"])
                minimum = (
                    0.9
                    if dimension["id"] in {"model_correctness", "validation_counterevidence"}
                    else 0.8
                )
                if ratio < minimum:
                    raise _fail(
                        f"quality dimension below threshold: {dimension['id']}"
                    )
                allowed_types = set(rubric.get(dimension["id"], []))
                for entity_id in dimension["evidence_ids"]:
                    record = runtime.registry.find_entity(entity_id)
                    if record["payload"].get("status") != "VALID":
                        raise _fail("quality dimension evidence is not VALID")
                    if record["entity_kind"] != "evidence":
                        raise _fail(
                            f"quality dimension evidence must be an evidence entity: {entity_id}"
                        )
                    evidence_type = record["payload"].get("evidence_type")
                    if evidence_type not in allowed_types:
                        raise _fail(
                            f"quality dimension {dimension['id']} evidence "
                            f"{entity_id} has type {evidence_type} outside its rubric"
                        )
                    previous = claimed_by_evidence.get(entity_id)
                    if previous is not None and previous != dimension["id"]:
                        raise _fail(
                            f"one evidence entity may support only one dimension: {entity_id}"
                        )
                    claimed_by_evidence[entity_id] = dimension["id"]
            for claim_id in quality["contribution_claim_ids"]:
                _valid(runtime, "claim", claim_id)
        elif stage == "P11":
            manifest = _evidence(runtime, "delivery_manifest")
            checksum = _evidence(runtime, "package_checksum")
            privacy = _evidence(runtime, "privacy_scan")
            if not manifest["files"] or checksum["archive_test"] != "PASS":
                raise _fail("delivery manifest or archive test is incomplete")
            if not re.fullmatch(r"[0-9a-f]{64}", checksum["sha256"]):
                raise _fail("package checksum is invalid")
            if privacy["status"] != "PASS":
                raise _fail("privacy scan did not pass; package is not deliverable")
            recomputed_scan = scan_manifest_files(runtime, manifest["files"])
            if recomputed_scan["status"] != "PASS" or recomputed_scan != privacy:
                raise _fail(
                    "registered privacy scan differs from the live recomputed scan"
                )
            distribution_licenses = manifest.get("distribution_licenses")
            if not isinstance(distribution_licenses, list):
                raise _fail("delivery manifest lacks distribution_licenses")
            licensed_entries: list[dict[str, Any]] = []
            for entry in distribution_licenses:
                if not isinstance(entry, dict):
                    raise _fail("distribution license entry must be an object")
                if not isinstance(entry.get("license"), str) or not entry["license"]:
                    raise _fail("distribution license entry lacks a license")
                if not isinstance(entry.get("distribution_allowed"), bool):
                    raise _fail("distribution license entry lacks distribution_allowed")
                if not (
                    isinstance(entry.get("artifact_id"), str)
                    or isinstance(entry.get("relative_path"), str)
                ):
                    raise _fail("distribution license entry lacks an artifact binding")
                licensed_entries.append(entry)
            for item in manifest["files"]:
                artifact = _valid(runtime, "artifact", item["artifact_id"])
                if artifact.get("artifact_type") in {"raw_data", "private_data"}:
                    covered = any(
                        (
                            entry.get("artifact_id") == artifact["entity_id"]
                            or entry.get("relative_path") == item["path"]
                        )
                        and entry.get("distribution_allowed") is True
                        for entry in licensed_entries
                    )
                    if not covered:
                        raise _fail(
                            f"restricted data is not licensed for distribution: {item['path']}"
                        )
            for entry in manifest["files"]:
                archive_path = entry.get("archive_path")
                if archive_path is None:
                    continue
                if not isinstance(archive_path, str) or not archive_path:
                    raise _fail("delivery archive_path must be a non-empty string")
                logical = Path(archive_path)
                if (
                    "\\" in archive_path
                    or logical.is_absolute()
                    or ".." in logical.parts
                    or any(
                        part in {"", ".", ".."} for part in logical.parts
                    )
                ):
                    raise _fail(f"delivery archive_path is unsafe: {archive_path}")
            package = _valid(
                runtime, "artifact", checksum["package_artifact_id"]
            )
            package_path = resolve_within(
                runtime.project_root,
                runtime.project_root / package["relative_path"],
                must_exist=True,
            )
            if package.get("sha256") != checksum["sha256"] or sha256_file(
                package_path
            ) != checksum["sha256"]:
                raise _fail("package checksum does not match registered artifact")
            package_events = [
                event
                for event in runtime.ledger.read_events()
                if event.get("event_type") == "PACKAGE_CREATED"
                and event.get("run_id") == runtime.run_id
                and event.get("payload", {}).get("sha256") == checksum["sha256"]
                and event.get("payload", {}).get("package_path")
                == package["relative_path"]
                and event.get("payload", {}).get("archive_test") == "PASS"
                and event.get("payload", {}).get("fresh_extract_test") == "PASS"
                and event.get("payload", {}).get("smoke_test") == "PASS"
            ]
            if len(package_events) != 1:
                raise _fail("package has no unique controlled creation event")
            manifest_records = _validate_manifest_items(runtime, manifest["files"])
            expected_files = {
                relative: record["sha256"]
                for relative, record in manifest_records.items()
            }
            archive_paths = {
                str(entry.get("archive_path", relative)): digest
                for relative, digest in expected_files.items()
                for entry in manifest["files"]
                if entry.get("path") == relative
            }
            if len(archive_paths) != len(expected_files):
                raise _fail("delivery archive_paths collide after case folding")
            try:
                with zipfile.ZipFile(package_path, "r") as archive:
                    if archive.testzip() is not None:
                        raise _fail("package archive CRC test failed")
                    names = archive.namelist()
                    folded_names = [name.casefold() for name in names]
                    if (
                        names != sorted(archive_paths)
                        or len(names) != len(set(names))
                        or len(folded_names) != len(set(folded_names))
                    ):
                        raise _fail("package members differ from delivery manifest")
                    for archive_name, digest in archive_paths.items():
                        if __import__("hashlib").sha256(archive.read(archive_name)).hexdigest() != digest:
                            raise _fail(
                                f"package member hash mismatch: {archive_name}"
                            )
            except (OSError, zipfile.BadZipFile, KeyError) as error:
                raise _fail("package archive cannot be verified") from error
        else:
            raise _fail(f"unknown stage: {stage}")
    except EvidenceInsufficientError as error:
        return CheckResult(
            rule_id=f"SEMANTIC-{stage}",
            status="FAIL",
            severity="MAJOR",
            reason=str(error),
            minimum_fix=[
                "fix the most upstream root cause, register new evidence, "
                "and re-run the affected gates"
            ],
            rerun_scope=_rerun_scope_for(runtime, stage),
        )
    except BlockedError as error:
        block = getattr(error, "block_payload", None)
        return CheckResult(
            rule_id=f"SEMANTIC-{stage}",
            status="BLOCKED",
            severity="MAJOR",
            reason=str(error),
            block=block,
        )
    except (IntegrityError, ConfigError) as error:
        return CheckResult(
            rule_id=f"SEMANTIC-{stage}",
            status="ERROR",
            severity="CRITICAL",
            reason=(
                f"stage state integrity error: {type(error).__name__}: {error}"
            ),
        )
    except Exception as error:
        return CheckResult(
            rule_id=f"SEMANTIC-{stage}",
            status="ERROR",
            severity="CRITICAL",
            reason=f"internal checker error: {type(error).__name__}: {error}",
        )
    return CheckResult(
        rule_id=f"SEMANTIC-{stage}",
        status="PASS",
        severity="MAJOR",
        reason="stage evidence structure, entity references, and critical semantics passed",
    )


def reconcile_changed_artifacts(runtime: Runtime) -> dict[str, Any]:
    changed: list[str] = []
    for record in runtime.registry.iter_latest("artifact"):
        payload = record["payload"]
        if payload.get("status") != "VALID":
            continue
        try:
            path = resolve_within(
                runtime.project_root,
                runtime.project_root / payload["relative_path"],
                must_exist=False,
            )
        except IntegrityError:
            changed.append(record["entity_id"])
            continue
        if (
            not path.is_file()
            or path.is_symlink()
            or sha256_file(path) != payload["sha256"]
        ):
            changed.append(record["entity_id"])
    affected: list[str] = []
    if changed:
        graph = LineageGraph(runtime.registry)
        affected = graph.invalidate_from(
            changed, "registered artifact content changed", root_status="INVALID"
        )
        state = runtime.workflow.state()
        reached = {
            stage
            for stage, status in state["stages"].items()
            if status != "NOT_STARTED"
        }
        # U1: derive the rollback target from the *provenance* of every
        # affected entity (created_stage, or execution payload stage), so a
        # changed P8 publication asset rolls back to P8 - never blindly to a
        # hard-coded fallback stage.
        candidate_stages: list[str] = []
        for entity_id in affected:
            kind = graph.kind_by_id[entity_id]
            record = runtime.registry.latest(kind, entity_id)
            payload = record["payload"]
            stage = record.get("created_stage")
            if kind == "execution":
                stage = payload.get("stage")
            if isinstance(stage, str) and stage in reached:
                candidate_stages.append(stage)
        if candidate_stages:
            rollback = min(candidate_stages, key=lambda s: int(s[1:]))
        else:
            raw_types = {"raw_data", "problem_statement"}
            rollback = (
                "P3"
                if any(
                    runtime.registry.latest("artifact", item)["payload"].get(
                        "artifact_type"
                    )
                    in raw_types
                    for item in changed
                )
                else "P5"
            )
        if rollback in reached:
            invalidate_stage_downstream(
                runtime.registry,
                rollback,
                "artifact hash changed; downstream evidence invalidated",
            )
            runtime.workflow.rollback(
                rollback, "artifact hash changed; downstream evidence invalidated"
            )
    return {"changed": sorted(changed), "affected": sorted(affected)}


def _domain_status(*statuses: str) -> str:
    if "ERROR" in statuses:
        return "ERROR"
    if "FAIL" in statuses:
        return "FAIL"
    if any(status in {"PASS", "NOT_APPLICABLE"} for status in statuses):
        return "PASS"
    return "NOT_APPLICABLE"


def run_domain_audit(runtime: Runtime) -> dict[str, Any]:
    """M12: read-only, domain-separated audit.

    Every domain produces its own status and detail; the aggregate can never
    hide a sub-domain ERROR behind a PASS.  No domain mutates the project.
    """
    domains: dict[str, Any] = {}

    def guard(name: str, checker) -> None:
        try:
            outcome = checker()
            if outcome is None:
                domains[name] = {"status": "PASS", "detail": "verified"}
            else:
                domains[name] = outcome
        except (IntegrityError, ConfigError) as error:
            domains[name] = {"status": "ERROR", "detail": str(error)}
        except EvidenceInsufficientError as error:
            domains[name] = {"status": "FAIL", "detail": str(error)}
        except Exception as error:
            domains[name] = {
                "status": "ERROR",
                "detail": f"{type(error).__name__}: {error}",
            }

    def integrity() -> dict[str, Any]:
        runtime.ledger.validate()
        runtime.registry.validate_integrity()
        return {"status": "PASS", "detail": "ledger and registry verify"}

    def lineage_domain() -> dict[str, Any]:
        LineageGraph(runtime.registry)
        return {"status": "PASS", "detail": "lineage DAG is acyclic and complete"}

    def evidence_domain() -> dict[str, Any]:
        invalid: list[str] = []
        for record in runtime.registry.iter_latest("evidence"):
            try:
                runtime.registry.validate_payload(
                    "evidence", record["payload"], resolve_dependencies=False
                )
            except (IntegrityError, ConfigError):
                invalid.append(record["entity_id"])
        if invalid:
            return {"status": "FAIL", "detail": "invalid evidence: " + ", ".join(invalid)}
        return {"status": "PASS", "detail": "all evidence schemas valid"}

    def bindings_domain() -> dict[str, Any]:
        failures: list[str] = []
        for record in runtime.registry.iter_latest("result"):
            if record["payload"].get("status") != "VALID":
                continue
            try:
                verify_result_source(runtime.project_root, runtime.registry, record["entity_id"])
            except (IntegrityError, ConfigError) as error:
                failures.append(f"{record['entity_id']}: {error}")
        if failures:
            return {"status": "FAIL", "detail": "; ".join(failures)}
        return {"status": "PASS", "detail": "all valid results bind to their sources"}

    def publication_domain() -> dict[str, Any]:
        manuscripts = [
            record
            for record in runtime.registry.iter_latest("evidence")
            if record["payload"].get("status") == "VALID"
            and record["payload"].get("evidence_type") == "manuscript_source"
        ]
        if not manuscripts:
            return {
                "status": "NOT_APPLICABLE",
                "detail": "no manuscript evidence yet",
            }
        content = manuscripts[0]["payload"].get("content")
        if not isinstance(content, dict):
            raise IntegrityError("manuscript evidence content invalid")
        source = _valid(runtime, "artifact", content["source_artifact_id"])
        manifest_artifact = _valid(
            runtime, "artifact", content["binding_manifest_artifact_id"]
        )
        manifest_path = resolve_within(
            runtime.project_root,
            runtime.project_root / manifest_artifact["relative_path"],
            must_exist=True,
        )
        try:
            manifest_value = json.loads(manifest_path.read_text("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise IntegrityError("cannot parse binding manifest") from error
        if manifest_value.get("binding_manifest_version") != 2:
            raise IntegrityError("binding manifest is not v2")
        source_path = resolve_within(
            runtime.project_root,
            runtime.project_root / source["relative_path"],
            must_exist=True,
        )
        verify_project_binding_manifest(
            runtime.project_root, source_path, manifest_value, runtime.registry
        )
        return {"status": "PASS", "detail": "publication closure verifies"}

    def compliance_domain() -> dict[str, Any]:
        rules = [
            record
            for record in runtime.registry.iter_latest("evidence")
            if record["payload"].get("status") == "VALID"
            and record["payload"].get("evidence_type") == "competition_rules"
        ]
        if not rules:
            return {
                "status": "NOT_APPLICABLE",
                "detail": "no competition rules evidence yet",
            }
        checks = evaluate_requirements(
            runtime, rules[0]["payload"].get("content", {}).get("requirements")
        )
        failed = [check for check in checks if check.get("status") != "PASS"]
        if failed:
            return {
                "status": "FAIL",
                "detail": "requirement checks failed: "
                + "; ".join(str(check["requirement_id"]) for check in failed),
            }
        return {"status": "PASS", "detail": f"{len(checks)} requirement checks pass"}

    def review_domain() -> dict[str, Any]:
        open_findings = [
            record["payload"]
            for record in runtime.registry.iter_latest("finding")
            if record["payload"].get("status") == "VALID"
            and record["payload"].get("finding_status") == "OPEN"
        ]
        critical = [
            item for item in open_findings if item.get("severity") in {"CRITICAL", "MAJOR"}
        ]
        if critical:
            return {
                "status": "FAIL",
                "detail": "open critical/major findings: "
                + ", ".join(str(item.get("finding_id")) for item in critical),
            }
        return {
            "status": "PASS",
            "detail": f"{len(open_findings)} open findings, none critical/major",
        }

    def delivery_domain() -> dict[str, Any]:
        packages = [
            record["payload"]
            for record in runtime.registry.iter_latest("artifact")
            if record["payload"].get("artifact_type") == "delivery_package"
            and record["payload"].get("status") == "VALID"
        ]
        if not packages:
            return {
                "status": "NOT_APPLICABLE",
                "detail": "no delivery package artifact yet",
            }
        package_path = resolve_within(
            runtime.project_root,
            runtime.project_root / packages[0]["relative_path"],
            must_exist=True,
        )
        try:
            with zipfile.ZipFile(package_path, "r") as archive:
                if archive.testzip() is not None:
                    raise IntegrityError("package CRC test failed")
        except (OSError, zipfile.BadZipFile) as error:
            raise IntegrityError(f"package archive invalid: {error}") from error
        return {"status": "PASS", "detail": "package archive CRC verified"}

    guard("integrity", integrity)
    guard("lineage", lineage_domain)
    guard("evidence", evidence_domain)
    guard("scientific-bindings", bindings_domain)
    guard("publication", publication_domain)
    guard("compliance", compliance_domain)
    guard("review", review_domain)
    guard("delivery", delivery_domain)

    from .release import compute_release_label

    integrity_ok = domains.get("integrity", {}).get("status") == "PASS"
    release = compute_release_label(runtime, integrity_ok=integrity_ok)
    domains["release-status"] = {
        "status": "PASS" if release["label"] != "NOT_READY" else "FAIL",
        "detail": release["label"],
    }
    aggregate = _domain_status(
        *(domain["status"] for domain in domains.values())
    )
    return {"status": aggregate, "domains": domains}


def _safe_delivery_relative(raw: Any) -> str:
    relative = normalize_relative_posix(raw, field="delivery path")
    if any(
        relative.casefold() == prefix[:-1].casefold()
        or relative.casefold().startswith(prefix.casefold())
        for prefix in FORBIDDEN_PACKAGE_PREFIXES
    ):
        raise IntegrityError(f"forbidden delivery path: {relative}")
    return relative


def create_delivery_archive(
    runtime: Runtime,
    manifest_path: Path | str,
    output_path: Path | str,
    candidate: bool,
    force_new_name: bool = False,
) -> dict[str, Any]:
    state = runtime.workflow.state()
    if candidate:
        if state["active_stage"] != "P11" or any(
            state["stages"][f"P{i}"] != "PASSED" for i in range(11)
        ):
            raise GateFailedError(
                "candidate package requires P11 active and P0-P10 passed"
            )
    elif not state["complete"]:
        raise GateFailedError("final package export requires COMPLETE")
    manifest_file = resolve_regular_file_within(
        runtime.project_root, manifest_path
    )
    try:
        manifest = json.loads(manifest_file.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GateFailedError("cannot read delivery manifest") from error
    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("files"), list)
        or not manifest["files"]
    ):
        raise GateFailedError("delivery manifest must contain at least one file")
    manifest_records = _validate_manifest_items(runtime, manifest["files"])
    entries: list[tuple[str, Path]] = []
    source_by_path: dict[str, str] = {}
    for relative, record in manifest_records.items():
        source = resolve_within(
            runtime.project_root,
            runtime.project_root / relative,
            must_exist=True,
        )
        archive_path = relative
        for item in manifest["files"]:
            if item.get("path") == relative:
                candidate_path = item.get("archive_path")
                if candidate_path is not None:
                    archive_path = _safe_archive_path(candidate_path)
        entries.append((archive_path, source))
        source_by_path[relative] = archive_path
    if len({path.casefold() for path, _ in entries}) != len(entries):
        raise IntegrityError("delivery archive paths collide after case folding")
    requested = Path(output_path)
    destination = resolve_within(
        runtime.project_root,
        requested if requested.is_absolute() else runtime.project_root / requested,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if force_new_name:
            stem, suffix = destination.stem, destination.suffix
            counter = 1
            while True:
                candidate_path = destination.with_name(f"{stem}-{counter}{suffix}")
                if not candidate_path.exists():
                    destination = candidate_path
                    break
                counter += 1
        else:
            raise IntegrityError(
                "delivery archive already exists; outputs are immutable"
                " (retry with --force-new-name to auto-number)"
            )
    if not candidate:
        previous_packages = [
            record["payload"]
            for record in runtime.registry.iter_latest("artifact")
            if record["payload"].get("artifact_type") == "delivery_package"
            and record["payload"].get("status") == "VALID"
        ]
        if len(previous_packages) != 1:
            raise IntegrityError(
                "final package requires exactly one verified candidate package"
            )
        final_candidate_sha = previous_packages[0].get("sha256")
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for archive_name, source in sorted(entries):
            info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes())
    with zipfile.ZipFile(destination, "r") as archive:
        bad = archive.testzip()
        expected_names = [item[0] for item in sorted(entries)]
        names = archive.namelist()
        folded_names = [name.casefold() for name in names]
        if (
            bad is not None
            or names != expected_names
            or len(names) != len(set(names))
            or len(folded_names) != len(set(folded_names))
        ):
            raise IntegrityError("delivery archive verification failed")
    smoke_command = manifest.get("smoke_command")
    if smoke_command is not None and (
        not isinstance(smoke_command, list)
        or not smoke_command
        or not all(isinstance(item, str) and item for item in smoke_command)
    ):
        raise IntegrityError("delivery manifest smoke_command must be a non-empty argument list")
    extraction = _verify_fresh_extraction(runtime, destination, entries)
    smoke_test = "NOT_REQUESTED"
    if smoke_command is not None:
        smoke_test = _run_fresh_smoke(runtime, destination, smoke_command)
    report = {
        "package_path": destination.relative_to(runtime.project_root).as_posix(),
        "package_artifact_id": "art_package_" + sha256_file(destination)[:16],
        "sha256": sha256_file(destination),
        "archive_test": "PASS",
        "fresh_extract_test": extraction["status"],
        "smoke_test": smoke_test,
        "files": [item[0] for item in sorted(entries)],
        "archive_paths": [item[0] for item in sorted(entries)],
        "candidate": candidate,
    }
    if not candidate:
        if report["sha256"] != final_candidate_sha:
            raise IntegrityError(
                "final package bytes differ from the gated candidate package"
            )
    package_artifact_id = "art_package_" + report["sha256"][:16]
    try:
        existing = runtime.registry.latest("artifact", package_artifact_id)["payload"]
        if existing.get("sha256") != report["sha256"]:
            raise IntegrityError(
                "package artifact ID collision with different bytes"
            )
    except IntegrityError:
        runtime.registry.register(
            "artifact",
            {
                "artifact_id": package_artifact_id,
                "run_id": runtime.run_id,
                "artifact_class": "production",
                "artifact_type": "delivery_package",
                "status": "VALID",
                "relative_path": report["package_path"],
                "sha256": report["sha256"],
                "size_bytes": destination.stat().st_size,
                "media_type": "application/zip",
                "inputs": [
                    str(item["artifact_id"])
                    for item in manifest["files"]
                    if isinstance(item, dict)
                ],
                "candidate": candidate,
            },
            stage="P11",
        )
    runtime.ledger.append(
        runtime.run_id, "PACKAGE_CREATED", report, stage="P11"
    )
    return report


def _safe_archive_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise IntegrityError("delivery archive_path must be a POSIX relative path")
    logical = Path(raw)
    if (
        logical.is_absolute()
        or ".." in logical.parts
        or any(part in {"", "."} for part in logical.parts)
        or any(
            str(raw).casefold() == prefix[:-1].casefold()
            or str(raw).casefold().startswith(prefix.casefold())
            for prefix in FORBIDDEN_PACKAGE_PREFIXES
        )
    ):
        raise IntegrityError(f"delivery archive_path is unsafe: {raw}")
    return logical.as_posix()


def _run_fresh_smoke(
    runtime: Runtime,
    archive_path: Path,
    smoke_command: list[str],
) -> str:
    """Execute the manifest's smoke command inside a fresh extraction.

    The smoke test proves the package is usable in a NEW directory that is
    unrelated to the project, not merely that its members hash correctly.
    The command runs with a bounded timeout and a minimal environment.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="mmflow-smoke-") as raw_directory:
        directory = Path(raw_directory)
        with zipfile.ZipFile(archive_path, "r") as archive:
            for info in archive.infolist():
                if info.filename.endswith("/"):
                    continue
                target = (directory / info.filename).resolve()
                if directory not in target.parents:
                    raise IntegrityError(f"smoke extraction escapes: {info.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
        try:
            completed = subprocess.run(
                smoke_command,
                cwd=directory,
                capture_output=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise IntegrityError(f"delivery smoke test failed: {type(error).__name__}") from error
        if completed.returncode != 0:
            raise IntegrityError(
                "delivery smoke test failed: "
                + completed.stderr.decode("utf-8", errors="replace")[:500]
            )
    return "PASS"


def _verify_fresh_extraction(
    runtime: Runtime,
    archive_path: Path,
    entries: list[tuple[str, Path]],
) -> dict[str, Any]:
    """Extract the package into a fresh directory outside the project and
    verify it is self-contained: no traversal, no absolute members, no
    reserved device names, and every member hash matches the manifest."""
    import tempfile

    expected = {name: sha256_file(source) for name, source in entries}
    with tempfile.TemporaryDirectory(prefix="mmflow-delivery-") as raw_directory:
        directory = Path(raw_directory)
        with zipfile.ZipFile(archive_path, "r") as archive:
            for info in archive.infolist():
                name = info.filename
                if (
                    name.startswith("/")
                    or ".." in Path(name).parts
                    or re.match(r"^[A-Za-z]:", name)
                ):
                    raise IntegrityError(f"package member escapes extraction: {name}")
                if (
                    not name.endswith("/")
                    and Path(name).name.upper().rstrip(".").split(".")[0]
                    in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
                        "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
                        "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
                ):
                    raise IntegrityError(f"package member is a reserved device name: {name}")
                target = (directory / name).resolve()
                if directory not in target.parents and target != directory:
                    raise IntegrityError(f"package member escapes extraction: {name}")
                if info.filename.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(info))
        for name, digest in expected.items():
            extracted = directory / name
            if not extracted.is_file():
                raise IntegrityError(f"package member missing after extraction: {name}")
            if sha256_file(extracted) != digest:
                raise IntegrityError(f"package member hash mismatch after extraction: {name}")
        entry_missing = [
            name
            for name in expected
            if not (directory / name).is_file()
        ]
        if entry_missing:
            raise IntegrityError(
                "package has no usable entry file after fresh extraction"
            )
        return {"status": "PASS", "extracted_members": len(expected)}
