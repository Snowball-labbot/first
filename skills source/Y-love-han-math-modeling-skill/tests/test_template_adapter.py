from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "integrate_templates", ROOT / "scripts" / "integrate_templates.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_cli_check_emits_structured_json_and_passes():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "integrate_templates.py"), "check", "--root", str(ROOT), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "PASS"
    assert report["template_count"] >= 5


def test_cli_list_contains_stage_and_dependency_metadata():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "integrate_templates.py"), "list", "--root", str(ROOT), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["templates"]
    assert all("stages" in entry and "inputs" in entry and "outputs" in entry for entry in report["templates"])


def test_copy_template_is_explicit_and_does_not_overwrite_existing(tmp_path: Path):
    manifest = {
        "schema": "math-modeling-template-manifest/v1",
        "version": 1,
        "templates": [
            {
                "id": "analytics.example",
                "category": "analytics",
                "path": "templates/example.py",
                "stages": ["P3"],
                "inputs": [],
                "outputs": [],
                "production_eligible": False,
            }
        ],
    }
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "example.py").write_text("print('example')\n", encoding="utf-8")
    destination = tmp_path / "project" / "example.py"
    destination.parent.mkdir()
    destination.write_text("existing\n", encoding="utf-8")

    result = MODULE.copy_template(
        tmp_path,
        manifest,
        "analytics.example",
        destination,
        project_root=tmp_path / "project",
    )

    assert result["status"] == "REFUSED"
    assert destination.read_text(encoding="utf-8") == "existing\n"


def test_copy_template_requires_external_project_root(tmp_path: Path):
    manifest = {
        "schema": "math-modeling-template-manifest/v1",
        "version": 1,
        "templates": [
            {
                "id": "analytics.example",
                "category": "analytics",
                "path": "templates/example.py",
                "stages": ["P3"],
                "inputs": [],
                "outputs": [],
                "production_eligible": False,
            }
        ],
    }
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "example.py").write_text("print('example')\n", encoding="utf-8")

    with pytest.raises(MODULE.TemplateManifestError, match="project-root"):
        MODULE.copy_template(tmp_path, manifest, "analytics.example", tmp_path / "example.py")

    with pytest.raises(MODULE.TemplateManifestError, match="skill root"):
        MODULE.copy_template(
            tmp_path,
            manifest,
            "analytics.example",
            tmp_path / "example.py",
            project_root=tmp_path,
        )


def test_copy_template_allows_an_external_project_root(tmp_path: Path):
    skill_root = tmp_path / "skill"
    external_project = tmp_path / "separate" / "project"
    (skill_root / "templates").mkdir(parents=True)
    external_project.mkdir(parents=True)
    (skill_root / "templates" / "example.py").write_text("print('example')\n", encoding="utf-8")
    manifest = {
        "schema": "math-modeling-template-manifest/v1",
        "version": 1,
        "templates": [
            {
                "id": "analytics.example",
                "category": "analytics",
                "path": "templates/example.py",
                "stages": ["P3"],
                "inputs": [],
                "outputs": [],
                "production_eligible": False,
            }
        ],
    }

    result = MODULE.copy_template(
        skill_root,
        manifest,
        "analytics.example",
        external_project / "example.py",
        project_root=external_project,
    )

    assert result["status"] == "COPIED"
    assert (external_project / "example.py").read_text(encoding="utf-8") == "print('example')\n"
