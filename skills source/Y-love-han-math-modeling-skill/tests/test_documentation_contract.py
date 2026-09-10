from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_validator_recognizes_visualization_and_expanded_hygiene():
    source = (ROOT / "scripts" / "validate_skill.py").read_text("utf-8")
    assert "templates/visualization" in source
    assert ".mypy_cache" in source and ".ruff_cache" in source
    assert "figure coverage" in source.lower() or "figure-coverage" in source.lower()


def test_figures_plan_cli_uses_external_project_output(tmp_path):
    project = tmp_path / "project"
    (project / ".mmflow").mkdir(parents=True)
    contract = project / "contract.json"
    contract.write_text(json.dumps({"questions": [{"question_id": "Q1"}]}), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmflow.py"), "figures", "plan", "--project", str(project), "--contract", "contract.json", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["schema"] == "mmflow-figure-coverage-plan/v1"
    assert (project / ".mmflow" / "figure-coverage-plan.json").is_file()

