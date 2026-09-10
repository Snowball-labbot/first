"""C01: stage epoch and evidence freshness locks."""

from __future__ import annotations

import pytest

from helpers import begin, build_through, gate, p0_evidence, reg

from scripts.mmflow_core.errors import IntegrityError
from scripts.mmflow_core.gates import evidence_freshness
from scripts.mmflow_core.lineage import invalidate_stage_downstream


def _fresh_record(created_stage="P0", stage_epoch=1):
    return {
        "created_stage": created_stage,
        "stage_epoch": stage_epoch,
        "payload": {"evidence_type": "capability_report"},
    }


def test_future_stage_evidence_registration_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    # P10 evidence registered during P0 must be rejected by the stage matrix.
    with pytest.raises(IntegrityError):
        reg(
            runtime,
            "evidence",
            {
                "evidence_id": "future_evidence",
                "evidence_type": "review_findings",
                "status": "VALID",
                "content": {
                    "finding_ids": [],
                    "open_by_severity": {"CRITICAL": 0, "MAJOR": 0, "MODERATE": 0, "MINOR": 0},
                    "independent_review": "limited",
                    "roles": [],
                },
                "supports": [],
            },
            stage="P0",
        )


def test_freshness_requires_current_epoch():
    current = _fresh_record("P0", 1)
    assert evidence_freshness(
        current, "P0", 1, {"P0": "ACTIVE"}, {}
    )["current"] is True
    stale = _fresh_record("P0", 1)
    assert evidence_freshness(
        stale, "P0", 2, {"P0": "ACTIVE"}, {}
    )["current"] is False
    future = _fresh_record("P10", 1)
    assert evidence_freshness(
        future, "P0", 1, {"P0": "ACTIVE"}, {}
    )["current"] is False


def test_cross_stage_inheritance_requires_passed_source():
    record = _fresh_record("P2", 1)
    record["payload"] = {"evidence_type": "problem_contract"}
    # Owning stage is ACTIVE (being redone) -> not inheritable.
    assert evidence_freshness(
        record, "P6", 1, {"P2": "ACTIVE", "P6": "ACTIVE"},
        {"problem_contract": ["P2"]},
    )["current"] is False
    # Owning stage PASSED in this generation -> inheritable.
    assert evidence_freshness(
        record, "P6", 1, {"P2": "PASSED", "P6": "ACTIVE"},
        {"problem_contract": ["P2"]},
    )["current"] is True


def test_rollback_invalidates_downstream_but_not_immutable_inputs(tmp_path):
    runtime, _ = build_through(tmp_path, "P2")
    invalidate_stage_downstream(runtime.registry, "P1", "rollback test")
    runtime.workflow.rollback("P1", "rollback test")
    assert runtime.registry.latest("evidence", "ev_contract")["payload"]["status"] == "STALE"
    assert runtime.registry.latest("evidence", "ev_inventory")["payload"]["status"] == "STALE"
    # P0 evidence and immutable external inputs survive.
    assert runtime.registry.latest("evidence", "ev_rules")["payload"]["status"] == "VALID"
    assert runtime.registry.latest("artifact", "art_problem")["payload"]["status"] == "VALID"
    # The re-entered stage is a new epoch.
    state = runtime.workflow.state()
    assert state["stage_epochs"]["P1"] == 2


def test_gate_rejects_superseded_epoch_evidence(tmp_path):
    runtime, _ = build_through(tmp_path, "P2")
    # Simulate an old epoch: roll back to P1 (epoch 2), then gate P1 with the
    # P1 evidence from epoch 1 -> must FAIL on freshness.
    invalidate_stage_downstream(runtime.registry, "P1", "rollback test")
    runtime.workflow.rollback("P1", "rollback test")
    report = gate(runtime, "P1")
    assert report["status"] == "FAIL"
    freshness_checks = [
        check for check in report["checks"] if check["rule_id"].startswith("EVIDENCE-")
    ]
    assert freshness_checks and all(
        check["status"] == "FAIL" for check in freshness_checks
    )
