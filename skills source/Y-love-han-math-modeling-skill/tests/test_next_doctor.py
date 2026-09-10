"""M01/N01/N02/N05: next work queue, read-only doctor, structured reports,
checkpoint v2."""

from __future__ import annotations

from helpers import begin, make_runtime, next_stage

from scripts.mmflow_core.project import create_checkpoint, doctor


def test_next_returns_unique_action_with_work_queue(tmp_path):
    runtime = make_runtime(tmp_path)
    begin(runtime, "P0")
    action = next_stage(runtime)
    assert action["stage"] == "P0"
    assert action["status"] == "ACTIVE"
    assert action["stage_epoch"] == 1
    assert action["next_command"] == "gate P0"
    assert set(action["missing_evidence"]) == {
        "capability_report",
        "competition_rules",
        "policy_lock",
    }
    assert action["rerun_scope"] == [f"P{i}" for i in range(12)]
    assert action["blocker"] is None
    assert action["active_redlines"] == []
    assert "references/workflow-contract.md" in action["references"]


def test_doctor_is_read_only_by_default(tmp_path):
    root = tmp_path / "not-a-project"
    result = doctor(str(root))
    assert result["filesystem"]["exists"] is False
    assert result["filesystem"]["write_probe"] is False
    assert not root.exists()  # doctor must not create the directory
    isolation = result["isolation"]
    assert isolation["os_sandbox"] is False
    assert isolation["network_isolation"] is False
    assert isolation["external_filesystem_isolation"] is False
    assert isolation["level"] == "project-directory-attestation"
    assert "does not block" in str(isolation["disclosure"])


def test_doctor_probe_write_is_explicit_opt_in(tmp_path):
    root = tmp_path / "probed"
    result = doctor(str(root), probe_write=True)
    assert result["filesystem"]["exists"] is True
    assert result["filesystem"]["writable"] is True
    probe = root / ".mmflow-doctor-write-probe"
    assert not probe.exists()  # the probe is cleaned up


def test_checkpoint_v2_carries_work_queue(tmp_path):
    runtime = make_runtime(tmp_path)
    begin(runtime, "P0")
    snapshot = create_checkpoint(runtime)
    assert snapshot["checkpoint_version"] == 2
    queue = snapshot["work_queue"]
    assert set(queue["missing_evidence"]) == {
        "capability_report",
        "competition_rules",
        "policy_lock",
    }
    assert queue["invalid_entities"] == []
    assert queue["rerun_scope"] == [f"P{i}" for i in range(12)]
    assert queue["unresolved_transactions"] is False


def test_gate_report_json_and_markdown_come_from_one_structure(completed_project):
    runtime = completed_project
    report = (
        runtime.project_root / ".mmflow/reports/000012_P11.json"
    )
    if not report.exists():
        reports = sorted(
            (runtime.project_root / ".mmflow/reports").glob("*_P11.json")
        )
        report = reports[-1]
    import json

    value = json.loads(report.read_text("utf-8"))
    markdown = (runtime.project_root / value["markdown_report_path"]).read_text("utf-8")
    # The markdown is rendered from the same check structure that was hashed.
    from scripts.mmflow_core.gates import verify_gate_report

    verify_gate_report(value, runtime.project_root)
    assert markdown  # non-empty
