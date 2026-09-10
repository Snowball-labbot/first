"""C04: gate error classification - FAIL vs ERROR must never be conflated."""

from __future__ import annotations

import json

import pytest

from helpers import build_through, reg

from scripts.mmflow_core.audit import semantic_stage_check


def _check_result(runtime, stage: str) -> dict:
    result = semantic_stage_check(runtime, stage)
    assert isinstance(result, dict) or hasattr(result, "rule_id")
    value = result if isinstance(result, dict) else {
        "rule_id": result.rule_id,
        "status": result.status,
        "severity": result.severity,
        "reason": result.reason,
    }
    return value


def test_missing_evidence_is_business_fail(tmp_path):
    # Empty project with no evidence at all -> FAIL, never ERROR.
    from helpers import begin, make_runtime

    runtime = make_runtime(tmp_path)
    begin(runtime, "P0")
    check = _check_result(runtime, "P0")
    assert check["status"] == "FAIL"
    assert check["severity"] == "MAJOR"


def test_corrupt_registry_is_integrity_error(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    # Tamper with a committed record file: content no longer matches its hash.
    evidence = runtime.registry.latest("evidence", "ev_rules")
    path = (
        runtime.project_root
        / ".mmflow/registry/evidence/ev_rules"
        / f"{evidence['entity_version']:06d}_{evidence['record_sha256']}.json"
    )
    value = json.loads(path.read_text("utf-8"))
    value["payload"]["content"]["requirements"] = [{"broken": True}]
    path.write_text(json.dumps(value), encoding="utf-8")
    check = _check_result(runtime, "P0")
    assert check["status"] == "ERROR"
    assert check["severity"] == "CRITICAL"
    assert "integrity" in check["reason"]


def test_injected_checker_exception_is_error(tmp_path, monkeypatch):
    runtime, _ = build_through(tmp_path, "P0")
    from scripts.mmflow_core import audit as audit_module

    def boom(*args, **kwargs):
        raise KeyError("internal failure")

    monkeypatch.setattr(audit_module, "_evidence", boom)
    check = _check_result(runtime, "P0")
    assert check["status"] == "ERROR"
    assert "internal checker error" in check["reason"]


def test_business_content_failure_stays_fail(tmp_path):
    runtime, _ = build_through(tmp_path, "P2")
    # A P3 audit on a P2 project is a business failure (missing evidence), not
    # an integrity error.  The audit itself is stage-driven and does not need
    # the stage to be active.
    check = _check_result(runtime, "P3")
    assert check["status"] == "FAIL"
