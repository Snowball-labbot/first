from __future__ import annotations

from helpers import (
    build_completed_project,
    P10_ROLES,
    reg,
)

from scripts.mmflow_core.release import compute_release_label, REVIEW_ROLES


def test_full_workflow_reaches_complete_and_limited_review(completed_project):
    runtime = completed_project
    state = runtime.workflow.state()
    assert state["complete"] is True
    assert all(state["stages"][f"P{i}"] == "PASSED" for i in range(12))

    label = compute_release_label(runtime)
    assert label["label"] == "SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW"
    assert "independent_review_unavailable" in label["caps"]

    # The label is derived from review evidence, not from the caller.
    modes = {
        record["payload"]["content"]["role"]
        for record in runtime.registry.iter_latest("evidence")
        if record["payload"]["evidence_type"] == "review_report"
    }
    assert modes == set(P10_ROLES)


def test_full_workflow_independent_review_reaches_full_label(tmp_path):
    runtime = build_completed_project(tmp_path, independent=True)
    label = compute_release_label(runtime)
    assert label["label"] == "SPECIAL_PRIZE_CANDIDATE"
    assert label["caps"] == []


def test_label_falls_back_to_not_ready_on_open_redline(completed_project):
    runtime = completed_project
    # A redline finding forces NOT_READY even when the workflow is COMPLETE.
    reg(
        runtime,
        "finding",
        {
            "finding_id": "finding_redline",
            "severity": "CRITICAL",
            "finding_status": "OPEN",
            "statement": "规则未核实红线",
            "affected_claims": [],
            "affected_entities": [],
            "rerun_scope": ["P10", "P11"],
            "evidence": [],
            "redline_id": "official_rules_unverified",
            "status": "VALID",
        },
        stage="P11",
    )
    label = compute_release_label(runtime)
    assert label["label"] == "NOT_READY"
    assert "active_redline" in label["caps"]


def test_registry_records_carry_epoch_metadata(completed_project):
    evidence = completed_project.registry.latest("evidence", "ev_contract")
    assert evidence["created_stage"] == "P2"
    assert isinstance(evidence["stage_epoch"], int) and evidence["stage_epoch"] >= 1
    assert isinstance(evidence["created_ledger_sequence"], int)


def test_gate_reports_are_structured_with_recovery_fields(completed_project):
    from helpers import gate

    runtime = completed_project
    # Roll back to P7 and gate without re-registering: the gate must FAIL with
    # structured recovery fields, never pass on stale evidence.
    from scripts.mmflow_core.lineage import invalidate_stage_downstream

    invalidate_stage_downstream(runtime.registry, "P7", "test rollback")
    runtime.workflow.rollback("P7", "test rollback")
    report = gate(runtime, "P7")
    assert report["status"] == "FAIL"
    checks = {check["rule_id"]: check for check in report["checks"]}
    semantic = checks["SEMANTIC-P7"]
    assert semantic["minimum_fix"]
    assert semantic["rerun_scope"] == ["P7", "P8", "P9", "P10", "P11"]
    # The markdown report must render the structured fields.
    markdown = (
        runtime.project_root / report["markdown_report_path"]
    ).read_text("utf-8")
    assert "## 最小修复动作" in markdown
    assert "## 必须重跑阶段" in markdown


def test_quality_review_ready_when_quality_passes_but_review_missing(completed_project):
    """When quality evidence is complete (adaptive profile passes by default)
    but review roles are missing, the label must be QUALITY_REVIEW_READY
    rather than REPRODUCIBLE.

    We take a fully completed project and revoke all review_report evidence.
    The release computation sees no review modes, but the quality contract
    (adaptive profile) still passes, so the label is QUALITY_REVIEW_READY.
    """
    from scripts.mmflow_core.lineage import LineageGraph

    runtime = completed_project

    # Revoke all review_report evidence so _review_modes returns empty.
    review_ids = [
        record["entity_id"]
        for record in runtime.registry.iter_latest("evidence")
        if record["payload"].get("evidence_type") == "review_report"
        and record["payload"].get("status") == "VALID"
    ]
    graph = LineageGraph(runtime.registry)
    graph.invalidate_from(review_ids, "test: simulate missing reviews")

    label = compute_release_label(runtime)
    assert label["label"] == "QUALITY_REVIEW_READY"
    assert "review_roles_incomplete" in label["caps"]


def test_reproducible_when_review_missing_and_quality_fails(completed_project):
    """When quality evidence is NOT complete and review roles are missing,
    the label must be REPRODUCIBLE.

    We take a fully completed project, revoke all review_report evidence
    (so review roles are missing), then switch the contract to a deep-insight
    profile that requires depth evidence we never registered.  The quality
    contract check fails, so the label falls back to REPRODUCIBLE.
    """
    import dataclasses
    from scripts.mmflow_core.lineage import LineageGraph

    runtime = completed_project

    # Revoke all review_report evidence so _review_modes returns empty.
    review_ids = [
        record["entity_id"]
        for record in runtime.registry.iter_latest("evidence")
        if record["payload"].get("evidence_type") == "review_report"
        and record["payload"].get("status") == "VALID"
    ]
    graph = LineageGraph(runtime.registry)
    graph.invalidate_from(review_ids, "test: simulate missing reviews")

    # Switch the runtime contract to a profile that requires depth evidence
    # we never registered.  quality_contract_check will then fail because
    # required depth evidence (e.g. candidate_rejection_record at P4) is
    # missing, forcing the label down to REPRODUCIBLE.
    modified_contract = dict(runtime.contract)
    modified_contract["quality_profile"] = "deep-insight"
    runtime = dataclasses.replace(runtime, contract=modified_contract)

    label = compute_release_label(runtime)
    assert label["label"] == "REPRODUCIBLE"
    assert "review_roles_incomplete" in label["caps"]


def test_integrity_failure_forces_not_ready(completed_project):
    """When registry integrity cannot be verified, the label must be
    NOT_READY with the integrity_failure cap, regardless of workflow state.
    """
    runtime = completed_project
    label = compute_release_label(runtime, integrity_ok=False)
    assert label["label"] == "NOT_READY"
    assert "integrity_failure" in label["caps"]
    assert label["reason"] == "registry or ledger integrity could not be verified"


def test_required_tests_failure_forces_not_ready(completed_project):
    """When a required test or validator fails, the label must be
    NOT_READY with the required_tests_failed cap, regardless of workflow state.
    """
    runtime = completed_project
    label = compute_release_label(runtime, tests_passed=False)
    assert label["label"] == "NOT_READY"
    assert "required_tests_failed" in label["caps"]
    assert label["reason"] == "a required test or validator failed"
