from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import IntegrityError

try:  # Windows
    import msvcrt  # type: ignore[import-not-found]

    _MSVCRT = True
except ImportError:  # pragma: no cover - platform dependent
    msvcrt = None
    _MSVCRT = False

try:  # POSIX
    import fcntl  # type: ignore[import-not-found]

    _FCNTL = True
except ImportError:  # pragma: no cover - platform dependent
    fcntl = None
    _FCNTL = False

if not _MSVCRT and not _FCNTL:  # pragma: no cover - unsupported platform
    raise RuntimeError("no OS-level file locking backend available")


class ProjectLock:
    """Cross-platform exclusive writer lock for one project.

    Every state-mutating command must hold this lock so Registry, ledger,
    gate reports, checkpoints, executions and packages cannot be written
    concurrently by two processes.  The lock file carries owner metadata
    (PID, start time, run_id) but ownership is decided by the OS advisory
    lock, never by the file's existence.
    """

    def __init__(self, project_root: Path | str, run_id: str | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.lock_dir = self.project_root / ".mmflow"
        self.lock_path = self.lock_dir / "project.lock"
        self.run_id = run_id
        self._handle: Any = None
        self._acquired = False

    def _open(self):
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        return open(self.lock_path, "a+b")

    @staticmethod
    def _acquire_os(handle: Any) -> None:
        if _MSVCRT:
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _release_os(handle: Any) -> None:
        if _MSVCRT:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def acquire(self) -> "ProjectLock":
        if self._acquired:
            raise IntegrityError("project lock is already held by this process")
        handle = self._open()
        try:
            self._acquire_os(handle)
        except OSError as error:
            handle.close()
            raise IntegrityError(
                "project is locked by another writer; retry after it finishes"
            ) from error
        self._handle = handle
        self._acquired = True
        metadata = {
            "lock_version": 1,
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "python_version": sys.version.split()[0],
        }
        handle.seek(0)
        handle.truncate()
        import json

        handle.write(
            json.dumps(
                metadata,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        )
        handle.flush()
        return self

    def release(self) -> None:
        if not self._acquired or self._handle is None:
            return
        try:
            self._release_os(self._handle)
        finally:
            self._handle.close()
            self._handle = None
            self._acquired = False

    def __enter__(self) -> "ProjectLock":
        return self.acquire()

    def __exit__(self, *exc: object) -> None:
        self.release()
