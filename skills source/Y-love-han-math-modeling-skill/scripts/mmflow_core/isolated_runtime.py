"""External, auditable execution areas for skill tooling.

The skill tree is treated as an immutable source.  Commands are copied to an
external snapshot and executed there with Python and tool caches redirected to
an external work directory.  A before/after manifest is retained so a tool
which ignores the environment contract cannot silently modify the source.

This module deliberately provides directory isolation and reproducibility
helpers; it is not an operating-system security sandbox.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


_EXCLUDED_DIRS = {
    ".git",
    ".mmflow",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
}
_EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".bak", ".swp", ".swo"}
_EXCLUDED_NAMES = {".coverage", ".coverage.sqlite"}
_MAX_WINDOWS_CWD_CHARS = 220


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_is_excluded(relative: Path) -> bool:
    return (
        any(part in _EXCLUDED_DIRS for part in relative.parts)
        or relative.suffix.lower() in _EXCLUDED_SUFFIXES
        or relative.name in _EXCLUDED_NAMES
    )


def _forbidden_members(root: Path) -> list[str]:
    if not root.exists():
        return []
    members: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if _relative_is_excluded(relative):
            members.append(relative.as_posix())
    return members


@dataclass(frozen=True)
class SourceManifest:
    """Hash inventory of every regular file in a source tree."""

    root: Path
    files: dict[str, str]


def build_source_manifest(root: Path | str) -> SourceManifest:
    resolved = Path(root).resolve()
    if not resolved.is_dir():
        raise ValueError(f"source root is not a directory: {resolved}")
    files: dict[str, str] = {}
    for path in sorted(resolved.rglob("*")):
        if path.is_file() and not path.is_symlink():
            files[path.relative_to(resolved).as_posix()] = _sha256(path)
    return SourceManifest(resolved, files)


@dataclass(frozen=True)
class CompletedRun:
    command: list[str]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


@dataclass(frozen=True)
class IsolationReport:
    ok: bool
    source_unchanged: bool
    source_diff: dict[str, list[str]]
    pollution: list[str]
    run_root: Path
    report_path: Path
    preserved_run_dir: bool
    purpose: str
    returncode: int | None
    last_command: list[str] | None


def _diff_manifests(before: SourceManifest, after: SourceManifest) -> dict[str, list[str]]:
    old, new = before.files, after.files
    return {
        "created": sorted(set(new) - set(old)),
        "deleted": sorted(set(old) - set(new)),
        "modified": sorted(path for path in set(old) & set(new) if old[path] != new[path]),
    }


def _copy_snapshot(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if _relative_is_excluded(relative):
            continue
        # Following an untrusted link could copy data outside the skill.  A
        # source symlink is therefore omitted from an isolated snapshot.
        if path.is_symlink():
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _short_workspace_root(purpose: str, preferred_parent: Path | None = None) -> Path:
    """Allocate a short external working directory for child processes.

    ``output_root`` is deliberately an audit/report destination and can live
    under a deeply nested project or pytest temporary directory.  It must not
    become the process working directory: Windows may reject such a cwd with
    ``WinError 267`` even though all path components exist.  Use the system
    temporary root (or, if configured too deeply, the current drive root) for
    the ephemeral snapshot while reports stay at the requested destination.
    """
    candidates: list[Path] = []
    if preferred_parent is not None:
        candidates.append(preferred_parent)
    try:
        candidates.append(Path(tempfile.gettempdir()))
    except OSError:
        pass
    drive_root = Path.cwd().anchor
    if drive_root:
        candidates.append(Path(drive_root))
    for parent in candidates:
        try:
            parent = parent.resolve()
            parent.mkdir(parents=True, exist_ok=True)
            run_root = Path(tempfile.mkdtemp(prefix="mmiso-", dir=str(parent)))
        except (OSError, ValueError):
            continue
        if len(str(run_root / "snapshot")) < _MAX_WINDOWS_CWD_CHARS:
            return run_root
        shutil.rmtree(run_root, ignore_errors=True)
    raise ValueError("cannot allocate a short external isolated workspace")


def _append_pytest_no_cache(value: str) -> str:
    tokens = value.split()
    if "-p" not in tokens or "no:cacheprovider" not in tokens:
        tokens.extend(["-p", "no:cacheprovider"])
    return " ".join(tokens)


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


@dataclass
class RunContext:
    source_root: Path
    snapshot_root: Path
    work_root: Path
    report_root: Path
    cache_root: Path
    before: SourceManifest
    run_root: Path
    purpose: str
    _last_run: CompletedRun | None = None

    def _environment(self) -> dict[str, str]:
        tmp = self.work_root / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1",
                "PYTHONPYCACHEPREFIX": str(self.cache_root),
                "TEMP": str(tmp),
                "TMP": str(tmp),
                "TMPDIR": str(tmp),
                "MYPY_CACHE_DIR": str(self.cache_root / "mypy"),
                "RUFF_CACHE_DIR": str(self.cache_root / "ruff"),
                "MMFLOW_ISOLATED_RUN": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            }
        )
        environment["PYTEST_ADDOPTS"] = _append_pytest_no_cache(
            environment.get("PYTEST_ADDOPTS", "")
        )
        return environment

    @staticmethod
    def _python_command(argv: Sequence[str]) -> list[str]:
        command = [str(item) for item in argv]
        if not command:
            raise ValueError("command must not be empty")
        executable = Path(command[0]).name.lower()
        if executable.startswith("python") and "-B" not in command[1:2]:
            command.insert(1, "-B")
        return command

    def command(
        self,
        argv: Sequence[str],
        *,
        timeout: float | None = None,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> CompletedRun:
        command = self._python_command(argv)
        working = (cwd or self.snapshot_root).resolve()
        allowed = self.snapshot_root == working or self.snapshot_root in working.parents
        if not allowed:
            raise ValueError("command cwd must be inside the isolated snapshot")
        started = time.monotonic()
        child_environment = self._environment()
        if environment:
            if not all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items()):
                raise ValueError("environment overrides must contain string keys and values")
            child_environment.update(environment)
        process = subprocess.Popen(
            command,
            cwd=str(working),
            env=child_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=(os.name != "nt"),
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            timed_out = True
            _terminate_process_tree(process)
            stdout, stderr = process.communicate()
            stderr = (stderr or "") + f"\ncommand timed out after {timeout} seconds"
            if not stdout and error.stdout:
                stdout = error.stdout if isinstance(error.stdout, str) else error.stdout.decode(errors="replace")
        result = CompletedRun(
            command=command,
            cwd=working,
            returncode=int(process.returncode if process.returncode is not None else 1),
            stdout=stdout or "",
            stderr=stderr or "",
            duration_seconds=round(time.monotonic() - started, 3),
            timed_out=timed_out,
        )
        self._last_run = result
        return result

    def finalize(
        self,
        *,
        success: bool,
        preserve_on_failure: bool = True,
    ) -> IsolationReport:
        after = build_source_manifest(self.source_root)
        diff = _diff_manifests(self.before, after)
        pollution = _forbidden_members(self.source_root)
        source_unchanged = not any(diff.values())
        ok = bool(success and source_unchanged and not pollution)
        preserve = (not ok and preserve_on_failure) or not success
        self.report_root.mkdir(parents=True, exist_ok=True)
        report_path = self.report_root / f"{self.purpose}-{self.run_root.name}.json"
        payload: dict[str, Any] = {
            "schema": "mmflow-isolation-report/v1",
            "purpose": self.purpose,
            "source_root": str(self.source_root),
            "run_root": str(self.run_root),
            "snapshot_root": str(self.snapshot_root),
            "work_root": str(self.work_root),
            "returncode": self._last_run.returncode if self._last_run else None,
            "last_command": self._last_run.command if self._last_run else None,
            "source_unchanged": source_unchanged,
            "source_diff": diff,
            "pollution": pollution,
            "ok": ok,
            "preserved_run_dir": preserve,
            "duration_seconds": self._last_run.duration_seconds if self._last_run else None,
            "stdout_tail": (self._last_run.stdout[-4000:] if self._last_run else ""),
            "stderr_tail": (self._last_run.stderr[-4000:] if self._last_run else ""),
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if not preserve:
            shutil.rmtree(self.run_root, ignore_errors=True)
        return IsolationReport(
            ok=ok,
            source_unchanged=source_unchanged,
            source_diff=diff,
            pollution=pollution,
            run_root=self.run_root,
            report_path=report_path,
            preserved_run_dir=preserve,
            purpose=self.purpose,
            returncode=self._last_run.returncode if self._last_run else None,
            last_command=self._last_run.command if self._last_run else None,
        )


def prepare_isolated_run(
    source_root: Path | str,
    purpose: str,
    *,
    output_root: Path | str | None = None,
) -> RunContext:
    source = Path(source_root).resolve()
    if not source.is_dir():
        raise ValueError(f"source root is not a directory: {source}")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose must be a non-empty string")
    if output_root is None:
        report_root = Path(tempfile.mkdtemp(prefix="mmflow-isolated-reports-")) / "reports"
        logical_parent = None
    else:
        report_parent = Path(output_root).resolve()
        if report_parent == source or source in report_parent.parents:
            raise ValueError("output root must be outside the source")
        report_parent.mkdir(parents=True, exist_ok=True)
        report_root = report_parent / "reports"
        logical_parent = report_parent
    try:
        run_root = _short_workspace_root(purpose, logical_parent)
    except ValueError:
        # If the caller selected a path too deep for Windows CreateProcess,
        # retain the report destination but place the logical run externally.
        run_root = _short_workspace_root(purpose)
    snapshot = run_root / "snapshot"
    work = run_root / "work"
    cache = work / "cache"
    before = build_source_manifest(source)
    work.mkdir(parents=True, exist_ok=True)
    _copy_snapshot(source, snapshot)
    return RunContext(
        source_root=source,
        snapshot_root=snapshot,
        work_root=work,
        report_root=report_root,
        cache_root=cache,
        before=before,
        run_root=run_root,
        purpose=purpose,
    )
