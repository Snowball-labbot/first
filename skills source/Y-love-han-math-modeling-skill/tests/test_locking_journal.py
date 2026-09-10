"""C03: single-writer lock and crash-recoverable registry journal."""

from __future__ import annotations

import json
import threading

import pytest

from helpers import build_through

from scripts.mmflow_core.errors import IntegrityError
from scripts.mmflow_core.locking import ProjectLock
from scripts.mmflow_core.registry import Registry


def test_project_lock_is_mutually_exclusive(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    root = runtime.project_root
    holder: ProjectLock | None = None
    second_error: Exception | None = None

    def hold():
        nonlocal holder, second_error
        holder = ProjectLock(root, runtime.run_id).acquire()
        # Keep the lock held for the duration of the test thread.
        threading.Event().wait(0.5)
        holder.release()

    thread = threading.Thread(target=hold)
    thread.start()
    import time

    time.sleep(0.1)
    try:
        ProjectLock(root, runtime.run_id).acquire()
    except IntegrityError as error:
        second_error = error
    thread.join()
    assert second_error is not None
    assert "locked by another writer" in str(second_error)
    # After release the lock is usable again.
    with ProjectLock(root, runtime.run_id):
        pass


def test_journal_abort_removes_uncommitted_record(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    root = runtime.project_root
    registry = Registry(root, runtime.ledger, runtime.run_id)
    # Simulate a crash between record write and ledger event.
    entity_dir = root / ".mmflow/registry/artifacts/art_orphan"
    entity_dir.mkdir(parents=True)
    record_path = entity_dir / "000001_abc.json"
    record = {
        "registry_version": 2,
        "entity_kind": "artifact",
        "entity_id": "art_orphan",
        "entity_version": 1,
        "run_id": runtime.run_id,
        "created_stage": "P0",
        "stage_epoch": 1,
        "created_ledger_sequence": 99999,
        "payload": {"artifact_id": "art_orphan"},
    }
    record["record_sha256"] = "a" * 64
    record_path.write_text(json.dumps(record), encoding="utf-8")
    journal = {
        "journal_version": 1,
        "kind": "artifact",
        "entity_id": "art_orphan",
        "entity_version": 1,
        "record_path": ".mmflow/registry/artifacts/art_orphan/000001_abc.json",
        "record_sha256": "a" * 64,
        "phase": "PREPARED",
    }
    (root / ".mmflow/registry-journal.json").write_text(
        json.dumps(journal), encoding="utf-8"
    )
    registry.validate_integrity()
    assert not (root / ".mmflow/registry-journal.json").exists()
    assert not record_path.exists()


def test_journal_commit_keeps_record_when_event_exists(tmp_path):
    from scripts.mmflow_core.canonical import canonical_json_bytes, sha256_bytes

    runtime, _ = build_through(tmp_path, "P0")
    root = runtime.project_root
    registry = Registry(root, runtime.ledger, runtime.run_id)
    entity_dir = root / ".mmflow/registry/artifacts/art_committed"
    entity_dir.mkdir(parents=True)
    record = {
        "registry_version": 2,
        "entity_kind": "artifact",
        "entity_id": "art_committed",
        "entity_version": 1,
        "run_id": runtime.run_id,
        "created_stage": "P0",
        "stage_epoch": 1,
        "created_ledger_sequence": 99999,
        "payload": {"artifact_id": "art_committed", "run_id": runtime.run_id},
    }
    record["record_sha256"] = sha256_bytes(canonical_json_bytes(record))
    record_path = entity_dir / f"000001_{record['record_sha256']}.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    runtime.ledger.append(
        runtime.run_id,
        "REGISTRY_RECORDED",
        {
            "kind": "artifact",
            "entity_id": "art_committed",
            "entity_version": 1,
            "record_path": ".mmflow/registry/artifacts/art_committed/000001_"
            + record["record_sha256"]
            + ".json",
            "record_sha256": record["record_sha256"],
        },
    )
    journal = {
        "journal_version": 1,
        "kind": "artifact",
        "entity_id": "art_committed",
        "entity_version": 1,
        "record_path": ".mmflow/registry/artifacts/art_committed/000001_"
        + record["record_sha256"]
        + ".json",
        "record_sha256": record["record_sha256"],
        "phase": "COMMITTED",
    }
    (root / ".mmflow/registry-journal.json").write_text(
        json.dumps(journal), encoding="utf-8"
    )
    registry.validate_integrity()
    assert not (root / ".mmflow/registry-journal.json").exists()
    assert record_path.exists()
