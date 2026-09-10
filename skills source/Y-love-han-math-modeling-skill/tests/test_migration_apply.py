from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import make_runtime
from scripts.mmflow_core.project import load_runtime
from scripts.mmflow_core.locking import ProjectLock
from scripts.mmflow_core.errors import GateFailedError, IntegrityError
from scripts.mmflow import _tree_sha256


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "mmflow.py"


def _make_v1(tmp_path: Path) -> Path:
    runtime = make_runtime(tmp_path)
    contract_path = runtime.project_root / ".mmflow" / "contract.json"
    contract = json.loads(contract_path.read_text("utf-8"))
    contract["contract_version"] = 1
    contract["skill_version"] = "1.0.0"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    return runtime.project_root


def test_migrate_apply_creates_loadable_v2_without_mutating_v1(tmp_path):
    source = _make_v1(tmp_path)
    before = (source / ".mmflow" / "contract.json").read_bytes()
    output = tmp_path / "migrated"
    completed = subprocess.run(
        [sys.executable, str(CLI), "migrate", "--project", str(source), "--apply", "--output", str(output), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "migration_applied"
    assert report["input_sha256"] and report["output_sha256"]
    assert report["v1_complete_mapping"] == "revalidation_required"
    assert (output / ".mmflow" / "contract.json").is_file()
    assert load_runtime(output)
    assert (source / ".mmflow" / "contract.json").read_bytes() == before


def test_migrate_apply_blocks_incompatible_contract_and_leaves_output_absent(tmp_path):
    source = _make_v1(tmp_path)
    contract_path = source / ".mmflow" / "contract.json"
    contract = json.loads(contract_path.read_text("utf-8"))
    contract["unsupported_future_field"] = {"ambiguous": True}
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    output = tmp_path / "blocked"
    completed = subprocess.run(
        [sys.executable, str(CLI), "migrate", "--project", str(source), "--apply", "--output", str(output), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert not output.exists()
    assert "incompatible" in completed.stderr.lower() or "incompatible" in completed.stdout.lower()


def test_migrate_apply_uses_external_backup_and_stable_report_digest(tmp_path):
    source = _make_v1(tmp_path)
    output = tmp_path / "nested" / "deliverables" / "migrated"
    completed = subprocess.run(
        [sys.executable, str(CLI), "migrate", "--project", str(source), "--apply", "--output", str(output), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    report_path = output / ".mmflow" / "migration-report.json"
    persisted = json.loads(report_path.read_text("utf-8"))
    backup = Path(report["backup"])

    assert output.is_dir()
    assert backup == output.parent / "migrated.migration-backup-v1"
    assert (backup / ".mmflow" / "contract.json").is_file()
    assert not (output / "migration-backup-v1").exists()
    assert persisted == report
    assert report["output_sha256"] == _tree_sha256(
        output, exclude_relative={".mmflow/migration-report.json"}
    )


def test_migrate_apply_removes_auxiliary_paths_if_final_promotion_fails(tmp_path, monkeypatch):
    """The v2 output and backup are all-or-nothing at the promotion edge."""
    source = _make_v1(tmp_path)
    output = tmp_path / "migrated"

    import scripts.mmflow as cli_module

    original_rename = Path.rename

    def fail_final_rename(self, target):
        if Path(self).name == "migrated.staging" and Path(target) == output:
            raise OSError("synthetic final promotion failure")
        return original_rename(self, target)

    monkeypatch.setattr(cli_module.Path, "rename", fail_final_rename)
    args = cli_module.build_parser().parse_args(
        ["migrate", "--project", str(source), "--apply", "--output", str(output), "--json"]
    )
    with pytest.raises(OSError, match="synthetic final promotion failure"):
        cli_module.dispatch(args)

    assert not output.exists()
    assert not output.with_name("migrated.staging").exists()
    assert not output.parent.joinpath("migrated.migration-backup-v1").exists()


def test_migrate_apply_is_atomic_when_report_write_fails(tmp_path, monkeypatch):
    """A report failure must not leave a promoted v2 project or backup."""
    source = _make_v1(tmp_path)
    output = tmp_path / "migrated"

    import scripts.mmflow as cli_module

    original_write_text = Path.write_text

    def fail_report_write(self, data, *args, **kwargs):
        if Path(self).name == "migration-report.json":
            raise OSError("synthetic migration report write failure")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_report_write)
    args = cli_module.build_parser().parse_args(
        ["migrate", "--project", str(source), "--apply", "--output", str(output), "--json"]
    )
    with pytest.raises(OSError, match="synthetic migration report write failure"):
        cli_module.dispatch(args)

    assert not output.exists()
    assert not output.with_name("migrated.staging").exists()
    assert not output.parent.joinpath("migrated.migration-backup-v1").exists()


def test_migrate_apply_honors_source_writer_lock(tmp_path):
    """Migration must serialize with ordinary project writers."""
    source = _make_v1(tmp_path)
    output = tmp_path / "migrated"
    holder = ProjectLock(source, "source-holder").acquire()
    try:
        args = __import__("scripts.mmflow", fromlist=["build_parser"]).build_parser().parse_args(
            ["migrate", "--project", str(source), "--apply", "--output", str(output), "--json"]
        )
        with pytest.raises(IntegrityError, match="locked by another writer"):
            __import__("scripts.mmflow", fromlist=["dispatch"]).dispatch(args)
    finally:
        holder.release()
    assert not output.exists()


def test_migrate_apply_does_not_delete_preexisting_staging_path(tmp_path):
    """A failed run may clean only auxiliary paths it owns."""
    source = _make_v1(tmp_path)
    output = tmp_path / "migrated"
    preexisting = output.with_name("migrated.staging")
    preexisting.mkdir()
    sentinel = preexisting / "owned-by-someone-else.txt"
    sentinel.write_text("keep", encoding="utf-8")
    args = __import__("scripts.mmflow", fromlist=["build_parser"]).build_parser().parse_args(
        ["migrate", "--project", str(source), "--apply", "--output", str(output), "--json"]
    )
    with pytest.raises(Exception, match="auxiliary path already exists"):
        __import__("scripts.mmflow", fromlist=["dispatch"]).dispatch(args)
    assert sentinel.read_text("utf-8") == "keep"


def _make_symlink_or_skip(link: Path, target: Path, *, is_dir: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=is_dir)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlink creation unavailable: {error}")


def test_migrate_apply_rejects_dangling_auxiliary_symlink_without_deleting_it(tmp_path):
    source = _make_v1(tmp_path)
    output = tmp_path / "migrated"
    staging_link = output.with_name("migrated.staging")
    _make_symlink_or_skip(staging_link, tmp_path / "missing-target")
    args = __import__("scripts.mmflow", fromlist=["build_parser"]).build_parser().parse_args(
        ["migrate", "--project", str(source), "--apply", "--output", str(output), "--json"]
    )
    with pytest.raises(GateFailedError, match="auxiliary path"):
        __import__("scripts.mmflow", fromlist=["dispatch"]).dispatch(args)
    assert staging_link.is_symlink()


def test_migrate_apply_rejects_symlink_in_source_tree(tmp_path):
    source = _make_v1(tmp_path)
    source_link = source / "inputs" / "external-link.txt"
    _make_symlink_or_skip(source_link, tmp_path / "outside.txt")
    output = tmp_path / "migrated"
    args = __import__("scripts.mmflow", fromlist=["build_parser"]).build_parser().parse_args(
        ["migrate", "--project", str(source), "--apply", "--output", str(output), "--json"]
    )
    with pytest.raises(IntegrityError, match="link"):
        __import__("scripts.mmflow", fromlist=["dispatch"]).dispatch(args)
    assert not output.exists()


def test_migrate_apply_validates_candidate_before_final_promotion(tmp_path, monkeypatch):
    source = _make_v1(tmp_path)
    output = tmp_path / "migrated"
    import scripts.mmflow as cli_module

    original_load_runtime = cli_module.load_runtime
    seen: list[Path] = []

    def fail_candidate_load(project_root, *args, **kwargs):
        candidate = Path(project_root)
        seen.append(candidate)
        if candidate.name == "migrated.staging":
            raise IntegrityError("synthetic candidate integrity failure")
        return original_load_runtime(project_root, *args, **kwargs)

    monkeypatch.setattr(cli_module, "load_runtime", fail_candidate_load)
    args = cli_module.build_parser().parse_args(
        ["migrate", "--project", str(source), "--apply", "--output", str(output), "--json"]
    )
    with pytest.raises(IntegrityError, match="synthetic candidate integrity failure"):
        cli_module.dispatch(args)
    assert any(path.name == "migrated.staging" for path in seen)
    assert not output.exists()
    assert not output.with_name("migrated.staging").exists()
    assert not output.parent.joinpath("migrated.migration-backup-v1").exists()


def test_migration_lock_paths_must_not_alias(tmp_path):
    from scripts.mmflow import _migration_locks

    source = tmp_path / ".migrated.mmflow-migration-lock"
    source.mkdir()
    output = tmp_path / "migrated"
    with pytest.raises(GateFailedError, match="lock paths"):
        with _migration_locks(source, output):
            pass
