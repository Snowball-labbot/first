"""C02: atomic BLOCKED lifecycle with structured payload and resolution evidence."""

from __future__ import annotations

import pytest

from helpers import begin, build_through, reg

from scripts.mmflow_core.errors import IntegrityError
from scripts.mmflow_core.gates import CheckResult
from scripts.mmflow_core.state_machine import Workflow

VALID_BLOCK = {
    "reason": "私有数据缺失",
    "missing_item": "inputs/private_data.csv",
    "why_required": "决定问题1的关键变量",
    "attempted_alternatives": ["公开替代数据"],
    "minimum_request": {"data_path": "需要参赛者提供私有数据路径"},
    "safe_partial_outputs": ["能力报告", "规则核验"],
    "resume_command": "resume --resolve-blocked --evidence <id>",
}


def test_block_requires_all_six_fields(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    with pytest.raises(IntegrityError):
        runtime.workflow.block("P0", {"reason": "x"})
    with pytest.raises(IntegrityError):
        runtime.workflow.block(
            "P0",
            {**VALID_BLOCK, "minimum_request": {}},
        )


def test_block_records_structured_state(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    event = runtime.workflow.block("P0", VALID_BLOCK)
    state = runtime.workflow.state()
    assert state["stages"]["P0"] == "BLOCKED"
    assert state["active_stage"] is None
    assert state["blocked"]["payload"]["missing_item"] == "inputs/private_data.csv"
    assert state["blocked"]["payload"]["resume_command"].startswith("resume")
    assert state["blocked"]["event_sequence"] == int(event["sequence"])


def test_resume_requires_post_block_evidence(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    # Evidence created before the block event.
    pre_block = reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_pre_block",
            "evidence_type": "given_value",
            "status": "VALID",
            "content": {"name": "pre"},
            "supports": [],
        },
        stage="P0",
    )
    _ = pre_block
    runtime.workflow.block("P0", VALID_BLOCK)

    def validator(evidence_id: str, block_event_sequence: int) -> None:
        record = runtime.registry.find_entity(evidence_id)
        if record["entity_kind"] != "evidence":
            raise IntegrityError("not evidence")
        if record["payload"].get("status") != "VALID":
            raise IntegrityError("not valid")
        if int(record.get("created_ledger_sequence", 0)) <= block_event_sequence:
            raise IntegrityError("predates block")

    with pytest.raises(IntegrityError):
        runtime.workflow.resume_blocked([], validator)
    with pytest.raises(IntegrityError):
        runtime.workflow.resume_blocked(["ev_pre_block"], validator)
    with pytest.raises(IntegrityError):
        runtime.workflow.resume_blocked(["ev_pre_block"])
    # Post-block evidence permits resumption; it is registered while the
    # workflow is BLOCKED, using the blocked stage.
    post_block = reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_post_block",
            "evidence_type": "given_value",
            "status": "VALID",
            "content": {"name": "post"},
            "supports": [],
        },
        stage="P0",
    )
    _ = post_block
    event = runtime.workflow.resume_blocked(["ev_post_block"], validator)
    state = runtime.workflow.state()
    assert state["active_stage"] == "P0"
    assert event["payload"]["resolution_evidence_ids"] == ["ev_post_block"]
    # The blocked work was not a discarded generation: the epoch stays, but
    # the previous gate result must not carry over.
    assert state["stage_epochs"]["P0"] == 1
    assert state["last_gate"].get("P0") is None


def test_blocked_check_result_requires_payload():
    with pytest.raises(ValueError):
        CheckResult(
            rule_id="X",
            status="BLOCKED",
            severity="MAJOR",
            reason="missing payload",
        ).validate()
    block_payload = {**VALID_BLOCK, "reason": "r"}
    result = CheckResult(
        rule_id="X",
        status="BLOCKED",
        severity="MAJOR",
        reason="r",
        block=block_payload,
    ).validate()
    assert result.block["minimum_request"]


def test_record_gate_rejects_blocked_status(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    with pytest.raises(IntegrityError):
        runtime.workflow.record_gate(
            "P0",
            {"status": "BLOCKED", "checks": [], "evidence_fingerprint": "x"},
            "x",
        )
