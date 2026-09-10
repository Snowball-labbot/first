from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from helpers import build_through, reg

ROOT = Path(__file__).resolve().parents[1]


def _load(project_root, skill_root):
    from scripts.mmflow_core.project import load_runtime

    return load_runtime(project_root, skill_root=skill_root)


def test_tampered_state_is_rejected_and_repaired(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    # Cold load: no cache exists yet, so this one takes the deep path and
    # writes the verified frontier.
    _load(runtime.project_root, runtime.skill_root)
    # Warm load: same frontier, so the fast trusted path engages.
    rt2 = _load(runtime.project_root, runtime.skill_root)
    assert getattr(rt2.workflow, "_trusted_view_ok", False) is True
    state_path = rt2.project_root / ".mmflow" / "state.json"
    original = json.loads(state_path.read_text("utf-8"))

    # Tamper: claim a stage that never ran.
    tampered = json.loads(json.dumps(original))
    tampered["stages"]["P5"] = "PASSED"
    state_path.write_text(json.dumps(tampered), encoding="utf-8")

    rt3 = _load(rt2.project_root, rt2.skill_root)
    # The loader must distrust the edited view and rebuild from events.
    assert rt3.workflow.state()["stages"]["P5"] != "PASSED"
    assert (
        rt3.workflow.state()["stages"]["P0"] == original["stages"]["P0"]
    )
    # After the repaired write the frontier trusts again.
    rt4 = _load(rt3.project_root, rt3.skill_root)
    assert getattr(rt4.workflow, "_trusted_view_ok", False) is True


def test_export_claims_feeds_qa_cards(tmp_path):
    runtime, _ = build_through(tmp_path, "P7")
    reg(
        runtime,
        "claim",
        {
            "claim_id": "claim_qa",
            "claim_type": "computed",
            "statement": "主模型RMSE为3.14",
            "status": "VALID",
            "supports": ["res_main"],
            "counterevidence": [],
            "scope": "给定数据集",
            "strength": "confirmed",
        },
        stage="P7",
    )

    payload_file = tmp_path / "claims_export.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "mmflow.py"),
            "export-claims",
            "--project",
            str(runtime.project_root),
            "--output",
            str(payload_file),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    exported = json.loads(payload_file.read_text("utf-8"))
    assert exported["schema"] == "mmflow-defense-cards-input/v1"
    target = next(c for c in exported["claims"] if c["claim_id"] == "claim_qa")
    assert target["statement"] == "主模型RMSE为3.14"
    assert target["supporting_result_ids"] == ["res_main"]

    cards = tmp_path / "答辩问答卡片.md"
    rendered = subprocess.run(
        [
            sys.executable,
            str(ROOT / "templates" / "presentation" / "qa_cards.py"),
            "--claims",
            str(payload_file),
            "--output",
            str(cards),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rendered.returncode == 0, rendered.stderr
    text = cards.read_text("utf-8")
    assert "claim_qa" in text and "主模型RMSE为3.14" in text
