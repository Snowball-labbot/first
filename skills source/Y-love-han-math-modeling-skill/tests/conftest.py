from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

import helpers

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))


@pytest.fixture()
def skill_root() -> Path:
    return SKILL_ROOT


@pytest.fixture(scope="session")
def completed_project_src(tmp_path_factory):
    """One full P0->P11->COMPLETE project built once per session."""
    path = tmp_path_factory.mktemp("completed-src") / "project"
    runtime = helpers.initialize_project(path, "CUMCM", "2026A", skill_root=SKILL_ROOT)
    helpers.build_completed_project(path, runtime=runtime)
    return path


@pytest.fixture()
def completed_project(tmp_path, completed_project_src):
    """A fast per-test copy of the shared completed project."""
    destination = tmp_path / "project"
    shutil.copytree(completed_project_src, destination)
    return helpers.load_runtime(destination, skill_root=SKILL_ROOT)


@pytest.fixture(scope="session")
def p11_project_src(tmp_path_factory):
    """A project at P11 ACTIVE with delivery evidence but no package yet."""
    path = tmp_path_factory.mktemp("p11-src") / "project"
    runtime = helpers.initialize_project(path, "CUMCM", "2026A", skill_root=SKILL_ROOT)
    runtime, _context = helpers.build_through(
        path, "P10", runtime=runtime
    )
    report = helpers.gate(runtime, "P10")
    assert report["status"] == "PASS"
    helpers.advance(runtime, "P10")
    helpers.begin(runtime, "P11")
    helpers.p11_delivery(runtime, package=False)
    return path


@pytest.fixture()
def p11_project(tmp_path, p11_project_src):
    """A fast per-test copy of the shared P11-active project."""
    destination = tmp_path / "project"
    shutil.copytree(p11_project_src, destination)
    return helpers.load_runtime(destination, skill_root=SKILL_ROOT)
