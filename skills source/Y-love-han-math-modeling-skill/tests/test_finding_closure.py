"""C05: findings can only be closed by a fully verified closure contract."""

from __future__ import annotations

import pytest

from helpers import build_through, gate, p3_evidence, reg

from scripts.mmflow_core.errors import IntegrityError


def _gate_record(runtime, stage: str) -> dict:
    events = [
        event
        for event in runtime.ledger.read_events()
        if event.get("event_type") == "GATE_RECORDED" and event.get("stage") == stage
    ]
    assert len(events) == 1
    return events[0]


def _finding_payload():
    return {
        "finding_id": "finding_x",
        "severity": "MAJOR",
        "finding_status": "OPEN",
        "statement": "P3 数据治理存在泄漏风险",
        "affected_claims": [],
        "affected_entities": [],
        "rerun_scope": ["P3"],
        "evidence": [],
        "status": "VALID",
    }


def _closure_evidence(runtime, finding_id: str, evidence_id: str) -> dict:
    return reg(
        runtime,
        "evidence",
        {
            "evidence_id": evidence_id,
            "evidence_type": "data_lineage",
            "status": "VALID",
            "content": {
                "sources": [{"artifact_id": "art_problem"}],
                "transforms": [],
                "splits": [],
                "finding_id": finding_id,
            },
            "supports": ["art_problem"],
        },
        stage="P3",
    )


def _closure(finding_id: str, rerun_gates: list[dict], evidence_ids: list[str]) -> dict:
    return {
        "finding_id": finding_id,
        "affected_entities": [],
        "repair_entities": [],
        "rerun_gates": rerun_gates,
        "closure_evidence_ids": evidence_ids,
    }


def test_finding_closes_with_verified_rerun_gate(tmp_path):
    runtime, _ = build_through(tmp_path, "P3")
    reg(runtime, "finding", _finding_payload(), stage="P3")
    report = gate(runtime, "P3")
    assert report["status"] == "PASS"
    record = _gate_record(runtime, "P3")
    closure_evidence = _closure_evidence(runtime, "finding_x", "ev_closure")
    _ = closure_evidence
    closed = runtime.registry.close_finding(
        "finding_x",
        _closure(
            "finding_x",
            [
                {
                    "stage": "P3",
                    "report_sha256": record["payload"]["report_sha256"],
                    "gate_event_sequence": int(record["sequence"]),
                }
            ],
            ["ev_closure"],
        ),
        "数据已补充并重跑 P3",
    )
    assert closed["payload"]["finding_status"] == "CLOSED"
    assert closed["payload"]["closure_status"] == "EVIDENCE_VERIFIED"


def test_unrelated_evidence_cannot_close_finding(tmp_path):
    runtime, _ = build_through(tmp_path, "P3")
    reg(runtime, "finding", _finding_payload(), stage="P3")
    report = gate(runtime, "P3")
    record = _gate_record(runtime, "P3")
    # Evidence that never references the finding.
    _closure_evidence(runtime, "other_finding", "ev_unrelated")
    with pytest.raises(IntegrityError):
        runtime.registry.close_finding(
            "finding_x",
            _closure(
                "finding_x",
                [
                    {
                        "stage": "P3",
                        "report_sha256": record["payload"]["report_sha256"],
                        "gate_event_sequence": int(record["sequence"]),
                    }
                ],
                ["ev_unrelated"],
            ),
            "unrelated evidence",
        )


def test_closure_evidence_must_postdate_finding(tmp_path):
    runtime, _ = build_through(tmp_path, "P3")
    # Evidence is created first, then the finding.
    _closure_evidence(runtime, "finding_x", "ev_early")
    reg(runtime, "finding", _finding_payload(), stage="P3")
    report = gate(runtime, "P3")
    record = _gate_record(runtime, "P3")
    with pytest.raises(IntegrityError):
        runtime.registry.close_finding(
            "finding_x",
            _closure(
                "finding_x",
                [
                    {
                        "stage": "P3",
                        "report_sha256": record["payload"]["report_sha256"],
                        "gate_event_sequence": int(record["sequence"]),
                    }
                ],
                ["ev_early"],
            ),
            "early evidence",
        )


def test_rerun_gate_must_postdate_finding(tmp_path):
    runtime, _ = build_through(tmp_path, "P3")
    # Gate P3 before creating the finding.
    report = gate(runtime, "P3")
    assert report["status"] == "PASS"
    old_record = _gate_record(runtime, "P3")
    reg(runtime, "finding", _finding_payload(), stage="P3")
    _closure_evidence(runtime, "finding_x", "ev_closure")
    with pytest.raises(IntegrityError):
        runtime.registry.close_finding(
            "finding_x",
            _closure(
                "finding_x",
                [
                    {
                        "stage": "P3",
                        "report_sha256": old_record["payload"]["report_sha256"],
                        "gate_event_sequence": int(old_record["sequence"]),
                    }
                ],
                ["ev_closure"],
            ),
            "old gate",
        )


def test_rerun_scope_must_be_covered(tmp_path):
    runtime, _ = build_through(tmp_path, "P3")
    reg(runtime, "finding", _finding_payload(), stage="P3")
    report = gate(runtime, "P3")
    record = _gate_record(runtime, "P3")
    _closure_evidence(runtime, "finding_x", "ev_closure")
    with pytest.raises(IntegrityError):
        runtime.registry.close_finding(
            "finding_x",
            _closure(
                "finding_x",
                [
                    {
                        "stage": "P2",
                        "report_sha256": record["payload"]["report_sha256"],
                        "gate_event_sequence": int(record["sequence"]),
                    }
                ],
                ["ev_closure"],
            ),
            "wrong stage",
        )


def test_wrong_report_hash_is_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P3")
    reg(runtime, "finding", _finding_payload(), stage="P3")
    gate(runtime, "P3")
    record = _gate_record(runtime, "P3")
    _closure_evidence(runtime, "finding_x", "ev_closure")
    with pytest.raises(IntegrityError):
        runtime.registry.close_finding(
            "finding_x",
            _closure(
                "finding_x",
                [
                    {
                        "stage": "P3",
                        "report_sha256": "0" * 64,
                        "gate_event_sequence": int(record["sequence"]),
                    }
                ],
                ["ev_closure"],
            ),
            "wrong hash",
        )
