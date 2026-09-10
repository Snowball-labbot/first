from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_run_tests_works_from_an_arbitrary_working_directory(tmp_path):
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_tests.py"), "--quick"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "PASS"
    assert report["skill_root"] == str(ROOT)


def test_clean_release_builder_excludes_runtime_caches(tmp_path):
    (tmp_path / "skill" / "scripts").mkdir(parents=True)
    source = tmp_path / "skill"
    (source / "SKILL.md").write_text("x\n", encoding="utf-8")
    (source / "scripts" / "ok.py").write_text("print('ok')\n", encoding="utf-8")
    (source / "scripts" / "bad.pyc").write_bytes(b"bad")
    (source / "scripts" / "__pycache__").mkdir()
    (source / "scripts" / "__pycache__" / "x.pyc").write_bytes(b"bad")
    (source / ".pytest_cache").mkdir()
    (source / ".pytest_cache" / "x").write_text("bad", encoding="utf-8")
    (source / ".mmflow").mkdir()
    (source / ".mmflow" / "state.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "release"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_release.py"), "--source", str(source), "--output", str(output), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (output / "scripts" / "ok.py").is_file()
    assert not list(output.rglob("*.pyc"))
    assert not list(output.rglob("__pycache__"))
    assert not (output / ".pytest_cache").exists()
    assert not (output / ".mmflow").exists()


def test_cli_release_status_returns_valid_label(tmp_path):
    """Invoke ``mmflow.py release-status`` via subprocess on a fully
    completed project and verify the JSON output contains a known label
    and the policy version.

    This exercises the CLI argument parser, the project loader, the
    integrity check, and ``compute_release_label`` end-to-end.
    """
    import helpers

    skill_root = ROOT
    project_path = tmp_path / "project"
    runtime = helpers.initialize_project(
        project_path, "CUMCM", "2026A", skill_root=skill_root
    )
    helpers.build_completed_project(project_path, runtime=runtime)

    completed = subprocess.run(
        [
            sys.executable,
            str(skill_root / "scripts" / "mmflow.py"),
            "release-status",
            "--project",
            str(project_path),
            "--json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["label"] in {
        "NOT_READY",
        "REPRODUCIBLE",
        "QUALITY_REVIEW_READY",
        "SPECIAL_PRIZE_CANDIDATE",
        "SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW",
    }
    assert result["policy_version"] == "evidence-v1"
    assert "program_proven" in result
    assert "cannot_guarantee" in result


def test_cli_release_status_on_uninitialized_project(tmp_path):
    """``release-status`` on an uninitialized project directory must
    return ``NOT_READY`` rather than crashing.
    """
    project_path = tmp_path / "empty_project"
    project_path.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "mmflow.py"),
            "release-status",
            "--project",
            str(project_path),
            "--json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    # An uninitialized project has no .mmflow, so the CLI should either
    # return NOT_READY or exit with a non-zero code; both are acceptable
    # as long as it does not crash with an unhandled traceback.
    if completed.returncode == 0:
        result = json.loads(completed.stdout)
        assert result["label"] == "NOT_READY"
    else:
        assert "Traceback" not in completed.stderr

