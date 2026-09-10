"""Contract tests for the clean delivery orchestrator.

These tests never write into the skill tree: packaging runs into pytest's
tmp_path, and the no-pollution assertion compares the skill file inventory
before and after the run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.clean_delivery import (
    CleanDeliveryError,
    _zip_member_is_safe,
    run_clean_delivery,
)


ROOT = Path(__file__).resolve().parents[1]


def _file_inventory(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )


def test_clean_delivery_rejects_output_inside_source(tmp_path):
    with pytest.raises(CleanDeliveryError, match="inside the source"):
        run_clean_delivery(ROOT, ROOT / "tmp", tests_mode="skip")


def test_clean_delivery_rejects_missing_source(tmp_path):
    with pytest.raises(CleanDeliveryError, match="not a directory"):
        run_clean_delivery(tmp_path / "absent", tmp_path / "out", tests_mode="skip")


def test_clean_delivery_rejects_existing_output(tmp_path):
    output = tmp_path / "release"
    output.mkdir()
    with pytest.raises(CleanDeliveryError, match="already exists"):
        run_clean_delivery(ROOT, output, tests_mode="skip")


@pytest.mark.parametrize(
    "member",
    ["/etc/passwd", "../escape.txt", "a/../../b", "tests/__pycache__/x.pyc", "y.pyc", ".coverage", ""],
)
def test_zip_member_safety_blocks_traversal_and_cachees(member):
    assert _zip_member_is_safe(member) is False


@pytest.mark.parametrize(
    "member",
    ["SKILL.md", "scripts/mmflow.py", "templates/analytics/utils.py"],
)
def test_zip_member_safety_allows_regular_paths(member):
    assert _zip_member_is_safe(member) is True


def test_clean_delivery_skip_mode_passes_without_polluting_source(tmp_path):
    before = _file_inventory(ROOT)

    report = run_clean_delivery(ROOT, tmp_path / "release", tests_mode="skip")

    assert report["status"] == "PASS", report
    assert report["steps"]["tests"]["status"] == "SKIP"
    assert report["clean_copy_preserved"] is None

    release_dir = tmp_path / "release"
    saved = json.loads((release_dir / "release_report.json").read_text("utf-8"))
    assert saved["schema"] == "math-modeling-clean-delivery/v1"
    assert saved["status"] == "PASS"
    zip_path = release_dir / "math-modeling-release.zip"
    assert zip_path.is_file()
    assert saved["steps"]["zip_safety"]["zip_sha256"]

    member_names = saved["steps"]["build_release"].get("sha256", {})
    assert member_names, "build_release must hash every delivered file"
    assert all(
        "__pycache__" not in name and ".pytest_cache" not in name
        for name in member_names
    )
    assert "templates/analytics/problem_reference_implementation.py" in member_names
    assert "scripts/clean_delivery.py" in member_names

    assert _file_inventory(ROOT) == before, "clean delivery must not pollute the skill tree"
