from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "scripts" / "run_tests.py"


def _mini_skill(tmp_path: Path) -> Path:
    skill = tmp_path / "mini-skill"
    (skill / "tests").mkdir(parents=True)
    (skill / "SKILL.md").write_text("mini\n", encoding="utf-8")
    (skill / "tests" / "test_ok.py").write_text(
        "from pathlib import Path\n"
        "def test_ok():\n"
        "    Path('unwanted.tmp').write_text('only in snapshot', encoding='utf-8')\n"
        "    assert True\n",
        encoding="utf-8",
    )
    (skill / "tests" / "conftest.py").write_text(
        "def pytest_load_initial_conftests(*args, **kwargs):\n"
        "    return None\n",
        encoding="utf-8",
    )
    return skill


def test_run_tests_unit_isolated_and_reports_progress(tmp_path):
    skill = _mini_skill(tmp_path)
    report_dir = tmp_path / "reports"
    completed = subprocess.run(
        [
            sys.executable,
            str(ENTRY),
            "--skill-root",
            str(skill),
            "--output-root",
            str(tmp_path / "runs"),
            "--unit",
            "tests/test_ok.py::test_ok",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        },
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "PASS"
    assert report["scope"] == "unit"
    assert report["returncode"] == 0
    assert report["source_diff"] == {"created": [], "deleted": [], "modified": []}
    assert report["pollution"] == []
    assert report["progress_events"]
    assert any('"event": "group_started"' in line for line in completed.stderr.splitlines())
    assert not (skill / "unwanted.tmp").exists()
    reproduction = report["reproduction"]["command"]
    assert "--skill-root" in reproduction
    assert str(skill) in reproduction
    assert "--unit" in reproduction
    assert "tests/test_ok.py::test_ok" in reproduction


def test_run_tests_rejects_unknown_scope(tmp_path):
    completed = subprocess.run(
        [sys.executable, str(ENTRY), "--scope", "unknown"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "invalid choice" in completed.stderr


def test_run_tests_accepts_quick_and_full_flags():
    source = ENTRY.read_text(encoding="utf-8")
    assert "--quick" in source
    assert "--full" in source


def test_run_tests_accepts_named_full_group_and_reproduces_it():
    source = ENTRY.read_text(encoding="utf-8")
    assert "--group" in source
    assert "group" in source
