from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from scripts.mmflow_core.isolated_runtime import (
    build_source_manifest,
    prepare_isolated_run,
)


def test_isolated_command_uses_external_cwd_and_cache_roots(tmp_path):
    source = tmp_path / "skill"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("skill\n", encoding="utf-8")
    (source / "scripts" / "write_probe.py").write_text(
        "from pathlib import Path\n"
        "import os\n"
        "Path('__pycache__').mkdir(exist_ok=True)\n"
        "Path('created.tmp').write_text('probe', encoding='utf-8')\n"
        "print(os.environ['PYTHONPYCACHEPREFIX'])\n"
        "print(os.environ['TEMP'])\n",
        encoding="utf-8",
    )

    context = prepare_isolated_run(source, "unit", output_root=tmp_path / "runs")
    before = build_source_manifest(source)
    completed = context.command([sys.executable, "scripts/write_probe.py"])
    report = context.finalize(success=completed.returncode == 0)

    assert completed.returncode == 0
    assert completed.cwd == context.snapshot_root
    assert str(context.cache_root) in completed.stdout
    assert str(context.work_root / "tmp") in completed.stdout
    assert report.source_unchanged is True
    assert report.ok is True
    assert build_source_manifest(source) == before
    assert not (source / "created.tmp").exists()
    assert not (source / "__pycache__").exists()
    assert not context.run_root.exists(), "successful runs should be cleaned"


def test_isolated_run_keeps_logical_run_under_normal_output_root(tmp_path):
    source = tmp_path / "skill"
    source.mkdir()
    (source / "SKILL.md").write_text("skill\n", encoding="utf-8")
    output_root = tmp_path / "runs"

    context = prepare_isolated_run(source, "normal", output_root=output_root)

    assert context.run_root.parent == output_root.resolve()
    context.finalize(success=False)


def test_isolated_run_rejects_source_descendant_output(tmp_path):
    source = tmp_path / "skill"
    source.mkdir()
    (source / "SKILL.md").write_text("skill\n", encoding="utf-8")

    with pytest.raises(ValueError, match="outside the source"):
        prepare_isolated_run(source, "bad", output_root=source / "results")


def test_isolated_run_uses_short_workspace_when_report_root_is_deep(tmp_path):
    """A nested isolated run must not inherit a Windows-invalid cwd.

    The report destination may legitimately be below a deep pytest/project
    directory.  Execution, however, must use a separate short external
    workspace so child tools can themselves launch subprocesses.
    """
    source = tmp_path / "skill"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("skill\n", encoding="utf-8")
    (source / "scripts" / "probe.py").write_text(
        "from pathlib import Path\n"
        "Path('ok.txt').write_text('ok', encoding='utf-8')\n",
        encoding="utf-8",
    )
    deep_reports = tmp_path
    for index in range(8):
        deep_reports = deep_reports / f"reports-{index:02d}-abcdefghij"

    context = prepare_isolated_run(source, "deep", output_root=deep_reports)
    completed = context.command([sys.executable, "scripts/probe.py"])
    report = context.finalize(success=completed.returncode == 0)

    assert completed.returncode == 0
    assert len(str(completed.cwd)) < 220
    assert str(deep_reports.resolve()) in str(report.report_path)
    assert report.source_unchanged is True
    assert report.ok is True


def test_failed_isolated_run_preserves_diagnostic_report(tmp_path):
    source = tmp_path / "skill"
    source.mkdir()
    (source / "SKILL.md").write_text("skill\n", encoding="utf-8")
    root = tmp_path / "runs"
    context = prepare_isolated_run(source, "failure", output_root=root)
    completed = context.command([sys.executable, "-c", "raise SystemExit(3)"])
    report = context.finalize(success=completed.returncode == 0)

    assert completed.returncode == 3
    assert report.ok is False
    assert report.preserved_run_dir is True
    assert context.run_root.exists()
    assert report.report_path.is_file()
    payload = json.loads(report.report_path.read_text("utf-8"))
    assert payload["returncode"] == 3
    assert payload["purpose"] == "failure"
