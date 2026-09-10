from __future__ import annotations

import hashlib
import importlib.metadata
import json
import locale
import math
import mimetypes
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical import (
    atomic_write_bytes,
    resolve_within,
    sha256_bytes,
    sha256_file,
)
from .errors import ConfigError, IntegrityError, UntrustedArtifactError
from .ledger import Ledger
from .registry import Registry


@dataclass(frozen=True)
class ExecutionRequest:
    stage: str
    question: str
    role: str
    artifact_class: str
    command: list[str]
    input_paths: list[str] = field(default_factory=list)
    code_paths: list[str] = field(default_factory=list)
    config_paths: list[str] = field(default_factory=list)
    source_artifact_ids: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    comparison_policies: dict[str, dict[str, Any]] = field(default_factory=dict)
    dataset_split_ids: list[str] = field(default_factory=list)
    random_protocol: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 3600
    output_encoding: str | None = None
    environment: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    execution: dict[str, Any]
    artifacts: list[dict[str, Any]]


class ExecutionRunner:
    def __init__(
        self,
        project_root: Path | str,
        ledger: Ledger,
        registry: Registry,
        run_id: str,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.ledger = ledger
        self.registry = registry
        self.run_id = run_id
        # relative path -> (size, mtime_ns) of the last hashed version; used
        # by the incremental project-snapshot fast path (same process only).
        self._snapshot_stat_cache: dict[str, tuple[int, int]] = {}

    @staticmethod
    def _is_link_or_junction(path: Path, stop: Path) -> bool:
        is_junction = getattr(os.path, "isjunction", lambda _path: False)
        current = path
        while True:
            if current.is_symlink() or is_junction(current):
                return True
            if current == stop:
                return False
            if stop not in current.parents:
                return True
            current = current.parent

    def _source(self, relative: str, production: bool) -> Path:
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise ConfigError("source paths must be non-empty POSIX relative paths")
        logical = Path(relative)
        if logical.is_absolute() or ".." in logical.parts:
            raise UntrustedArtifactError(f"source path escapes project: {relative}")
        path = resolve_within(
            self.project_root,
            self.project_root / logical,
            must_exist=True,
        )
        normalized = path.relative_to(self.project_root).as_posix()
        if production and any(
            normalized == prefix or normalized.startswith(prefix + "/")
            for prefix in ("legacy", "templates/examples", "tests/fixtures")
        ):
            raise UntrustedArtifactError(f"production execution cannot use {normalized}")
        if not path.is_file() or self._is_link_or_junction(path, self.project_root):
            raise UntrustedArtifactError(f"source is not a regular in-project file: {normalized}")
        return path

    def _copy_sources(
        self, request: ExecutionRequest, sandbox: Path
    ) -> list[dict[str, Any]]:
        production = request.artifact_class == "production"
        snapshots: list[dict[str, Any]] = []
        seen: dict[str, str] = {}
        for role, relatives in (
            ("input", request.input_paths),
            ("code", request.code_paths),
            ("config", request.config_paths),
        ):
            for relative in relatives:
                source = self._source(relative, production)
                normalized = source.relative_to(self.project_root).as_posix()
                if normalized in seen and seen[normalized] != role:
                    raise ConfigError(f"source has two roles: {normalized}")
                if normalized in seen:
                    continue
                seen[normalized] = role
                destination = sandbox / Path(normalized)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination, follow_symlinks=False)
                snapshots.append(
                    {
                        "role": role,
                        "relative_path": normalized,
                        "sha256": sha256_file(source),
                        "size_bytes": source.stat().st_size,
                    }
                )
        return sorted(snapshots, key=lambda item: (item["role"], item["relative_path"]))

    def _verify_source_artifacts(
        self, request: ExecutionRequest, snapshots: list[dict[str, Any]]
    ) -> None:
        if request.artifact_class != "production":
            return
        by_path = {item["relative_path"]: item for item in snapshots}
        if len(request.source_artifact_ids) != len(set(request.source_artifact_ids)):
            raise UntrustedArtifactError("source artifact IDs must be unique")
        if len(request.source_artifact_ids) != len(by_path):
            raise UntrustedArtifactError(
                "production execution requires one registered source artifact per source file"
            )
        covered: set[str] = set()
        for artifact_id in request.source_artifact_ids:
            try:
                artifact = self.registry.latest("artifact", artifact_id)["payload"]
            except IntegrityError as error:
                raise UntrustedArtifactError(f"unknown source artifact: {artifact_id}") from error
            if artifact["status"] != "VALID" or artifact["artifact_class"] not in {
                "external",
                "production",
            }:
                raise UntrustedArtifactError(f"source artifact is not eligible: {artifact_id}")
            relative = artifact["relative_path"]
            snapshot = by_path.get(relative)
            if snapshot is None or snapshot["sha256"] != artifact["sha256"]:
                raise UntrustedArtifactError(
                    f"source artifact does not match execution snapshot: {artifact_id}"
                )
            covered.add(relative)
        if covered != set(by_path):
            raise UntrustedArtifactError("source artifact coverage is incomplete")

    @staticmethod
    def _decode_log(data: bytes, requested: str | None) -> tuple[str, dict[str, Any]]:
        candidates: list[str] = []
        for encoding in (requested, "utf-8"):
            if encoding and encoding.lower() not in {item.lower() for item in candidates}:
                candidates.append(encoding)
        for encoding in candidates:
            try:
                return data.decode(encoding), {
                    "encoding": encoding,
                    "lossy": False,
                    "preferred_encoding": locale.getpreferredencoding(False),
                }
            except (UnicodeDecodeError, LookupError):
                continue
        encoding = requested or "utf-8"
        try:
            text = data.decode(encoding, errors="replace")
        except LookupError:
            encoding = "utf-8"
            text = data.decode("utf-8", errors="replace")
        return text, {
            "encoding": encoding,
            "lossy": True,
            "preferred_encoding": locale.getpreferredencoding(False),
        }

    SENSITIVE_ENV_KEY = re.compile(
        r"(?i)(token|password|passwd|secret|api[_-]?key|private[_-]?key|"
        r"credential|authorization|session)"
    )

    @staticmethod
    def _safe_environment(
        request: ExecutionRequest,
        output_dir: Path,
        *,
        cache_root: Path | None = None,
    ) -> dict[str, str]:
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in request.environment.items()):
            raise ConfigError("execution environment keys and values must be strings")
        sensitive = [
            key
            for key in request.environment
            if ExecutionRunner.SENSITIVE_ENV_KEY.search(key)
        ]
        if sensitive:
            raise ConfigError(
                "execution environment may not carry secrets; rejected keys: "
                + ", ".join(sorted(sensitive))
            )
        allowed = (
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "PATHEXT",
            "TEMP",
            "TMP",
            "COMSPEC",
            "LD_LIBRARY_PATH",
            "DYLD_LIBRARY_PATH",
        )
        environment = {key: os.environ[key] for key in allowed if key in os.environ}
        cache = (cache_root or output_dir.parent / "runtime-cache").resolve()
        temp = (cache.parent / "tmp").resolve()
        cache.mkdir(parents=True, exist_ok=True)
        temp.mkdir(parents=True, exist_ok=True)
        environment.update(
            {
                "PYTHONUTF8": "1",
                "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": str(cache),
                "TEMP": str(temp),
                "TMP": str(temp),
                "TMPDIR": str(temp),
                "MYPY_CACHE_DIR": str(cache / "mypy"),
                "RUFF_CACHE_DIR": str(cache / "ruff"),
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTEST_ADDOPTS": "-p no:cacheprovider",
                "MMFLOW_OUTPUT_DIR": str(output_dir),
                "MMFLOW_ARTIFACT_CLASS": request.artifact_class,
            }
        )
        reserved = {
            "MMFLOW_OUTPUT_DIR",
            "MMFLOW_ARTIFACT_CLASS",
            "MMFLOW_EXECUTION_ID",
            "MMFLOW_ATTEMPT_ID",
            "MMFLOW_RUN_ID",
            "PYTHONUTF8",
            "PYTHONHASHSEED",
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONPYCACHEPREFIX",
            "TEMP",
            "TMP",
            "TMPDIR",
            "MYPY_CACHE_DIR",
            "RUFF_CACHE_DIR",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "PYTEST_ADDOPTS",
        }
        conflict = reserved.intersection(request.environment)
        if conflict:
            raise ConfigError(f"execution environment overrides reserved keys: {sorted(conflict)}")
        environment.update(request.environment)
        return environment

    @staticmethod
    def _environment_lock() -> dict[str, str]:
        """Freeze installed distributions: name -> version, deterministic."""
        try:
            distributions = sorted(
                importlib.metadata.distributions(),
                key=lambda dist: str(dist.metadata.get("Name", "")).lower(),
            )
            return {
                str(dist.metadata.get("Name", "")).lower(): str(dist.version)
                for dist in distributions
                if dist.metadata.get("Name")
            }
        except Exception:
            return {}

    @staticmethod
    def _source_imports(
        project_root: Path, code_snapshots: list[dict[str, Any]]
    ) -> dict[str, list[str]]:
        """Record the top-level import closure of every code source.

        Dynamic imports cannot be proven statically; the recorded closure is
        the deterministic, auditable approximation and must be reviewed with
        the run itself.  Local modules referenced by these imports must be
        declared code/input sources (they are only usable from the sandbox).
        """
        imports: dict[str, list[str]] = {}
        pattern = re.compile(
            r"^\s*(?:import\s+([A-Za-z_][A-Za-z0-9_.]*)|"
            r"from\s+([A-Za-z_][A-Za-z0-9_.]*)\s+import\s+)",
            re.MULTILINE,
        )
        for snapshot in code_snapshots:
            relative = snapshot.get("relative_path")
            if not isinstance(relative, str):
                continue
            try:
                text = (project_root / relative).read_text("utf-8", errors="replace")
            except OSError:
                imports[relative] = []
                continue
            found: list[str] = []
            for match in pattern.finditer(text):
                module = match.group(1) or match.group(2)
                top = module.split(".")[0]
                if top and top not in found and top not in {"__future__", "os", "sys"}:
                    found.append(top)
            imports[relative] = sorted(found)
        return imports

    @staticmethod
    def _terminate_process_tree(pid: int | None) -> None:
        """Kill the whole process tree after a timeout, not only the parent."""
        if pid is None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                )
            else:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (OSError, subprocess.TimeoutExpired):
            pass

    @staticmethod
    def _logical_output_path(value: str) -> str:
        if not isinstance(value, str) or not value or "\\" in value:
            raise ConfigError("expected output must use a non-empty POSIX path")
        logical = Path(value)
        if logical.is_absolute() or ".." in logical.parts or value.endswith("/"):
            raise ConfigError(f"unsafe expected output path: {value}")
        return logical.as_posix()

    @classmethod
    def _comparison_contract(
        cls, request: ExecutionRequest
    ) -> tuple[list[str], dict[str, dict[str, Any]]]:
        outputs = [cls._logical_output_path(item) for item in request.expected_outputs]
        policies = {
            cls._logical_output_path(item): dict(policy)
            for item, policy in request.comparison_policies.items()
        }
        if len(outputs) != len(set(outputs)):
            raise ConfigError("expected output paths must be unique")
        if request.artifact_class == "production" and set(outputs) != set(policies):
            raise ConfigError(
                "production execution requires exactly one comparison policy per expected output"
            )
        for logical_path, policy in policies.items():
            mode = policy.get("mode")
            if mode not in {"sha256", "json_exact", "json_numeric", "statistical_json"}:
                raise ConfigError(f"unsupported comparison policy for {logical_path}")
            if mode in {"json_numeric", "statistical_json"}:
                for key in ("absolute_tolerance", "relative_tolerance"):
                    value = policy.get(key)
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(float(value))
                        or float(value) < 0
                    ):
                        raise ConfigError(
                            f"{mode} requires non-negative finite {key} for {logical_path}"
                        )
                if mode == "statistical_json":
                    statistic = policy.get("statistic")
                    if not isinstance(statistic, str) or statistic not in {
                        "mean",
                        "median",
                        "max_abs",
                    }:
                        raise ConfigError(
                            f"statistical_json requires a frozen statistic for {logical_path}"
                        )
                    for key in ("n_seeds", "min_sample_size"):
                        value = policy.get(key)
                        if (
                            isinstance(value, bool)
                            or not isinstance(value, int)
                            or value <= 0
                        ):
                            raise ConfigError(
                                f"statistical_json requires positive {key} for {logical_path}"
                            )
        return outputs, policies

    @staticmethod
    def _snapshot_files(root: Path) -> dict[str, str]:
        if not root.exists():
            return {}
        snapshot: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                snapshot[path.relative_to(root).as_posix()] = sha256_file(path)
        return snapshot

    @staticmethod
    def _diff_snapshots(
        before: dict[str, str], after: dict[str, str]
    ) -> tuple[list[str], list[str], list[str]]:
        created = sorted(set(after) - set(before))
        deleted = sorted(set(before) - set(after))
        modified = sorted(
            path for path in set(before) & set(after) if before[path] != after[path]
        )
        return created, modified, deleted

    def _project_snapshot(
        self, excluded_attempt: Path, previous: dict[str, str] | None = None
    ) -> dict[str, str]:
        """Full-project SHA-256 snapshot.

        ``previous`` (the pre-execution snapshot of the same attempt) enables
        an incremental fast path: when a file's size and mtime_ns are both
        unchanged since the previous snapshot, its hash is reused instead of
        re-reading every byte.  Any stat change still triggers a full hash,
        so correctness for real edits is preserved; only untouched files are
        skipped.  The threat model already excludes local attackers with
        filesystem-write access (workflow-contract.md), so mtime spoofing is
        out of scope.
        """
        previous = previous or {}
        snapshot: dict[str, str] = {}
        for path in sorted(self.project_root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            if path == excluded_attempt or excluded_attempt in path.parents:
                continue
            # The writer lock file is held open and byte-locked by this same
            # process for the whole command; reading it (as on Windows, where
            # byte-range locks block all other handles) would fail every
            # controlled execution. Its content is audit metadata only and is
            # never a model input, so it is excluded from the project snapshot.
            if path.name == "project.lock" and ".mmflow" in path.parts:
                continue
            relative = path.relative_to(self.project_root).as_posix()
            try:
                stat = path.stat()
            except OSError:
                stat = None
            prior_hash = previous.get(relative)
            cached_hash = self._snapshot_stat_cache.get(relative)
            if (
                prior_hash is not None
                and cached_hash is not None
                and stat is not None
                and cached_hash == (stat.st_size, stat.st_mtime_ns)
            ):
                snapshot[relative] = prior_hash
                continue
            digest = sha256_file(path)
            snapshot[relative] = digest
            if stat is not None:
                self._snapshot_stat_cache[relative] = (stat.st_size, stat.st_mtime_ns)
        return snapshot

    @staticmethod
    def _copy_directory_contents(source: Path, destination: Path) -> None:
        """Copy a run workspace while preserving relative POSIX semantics.

        Windows can reject a perfectly valid project path as a process cwd
        once a pytest temporary root and the auditable ``runs/<run_id>`` path
        are combined.  The runner therefore executes from a short external
        workspace and mirrors its evidence back into the logical attempt
        directory after the child exits.
        """
        destination.mkdir(parents=True, exist_ok=True)
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            target = destination / relative
            if path.is_symlink():
                raise UntrustedArtifactError(
                    f"execution workspace contains a symbolic link: {relative.as_posix()}"
                )
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)

    @classmethod
    def _short_execution_workspace(cls, logical_sandbox: Path) -> tuple[Path, Path]:
        """Create a short external workspace for ``CreateProcess``.

        The returned pair is ``(workspace_root, sandbox)``.  The workspace is
        deliberately outside the project so it cannot be mistaken for
        publishable evidence; callers must copy the sandbox back to the
        logical attempt before registering artifacts.
        """
        # ``tempfile`` normally chooses the system TEMP directory, which is
        # substantially shorter than a nested pytest/project path.  If an
        # administrator has configured a long TEMP, retry under the current
        # drive's root-adjacent temporary directory.
        candidates: list[Path] = []
        try:
            candidates.append(Path(tempfile.gettempdir()))
        except OSError:
            pass
        candidates.extend([Path(os.environ.get("TEMP", "")), Path.cwd().anchor and Path(Path.cwd().anchor)])
        workspace_root: Path | None = None
        for parent in candidates:
            if not str(parent):
                continue
            try:
                parent = parent.resolve()
                parent.mkdir(parents=True, exist_ok=True)
                candidate = Path(tempfile.mkdtemp(prefix="mmx-", dir=str(parent)))
            except (OSError, ValueError):
                continue
            if len(str(candidate / "sandbox")) < 240:
                workspace_root = candidate
                break
            shutil.rmtree(candidate, ignore_errors=True)
        if workspace_root is None:
            # Keep the error explicit: silently falling back to the deep path
            # would recreate the same Windows launch failure.
            raise IntegrityError("cannot allocate a short execution workspace")
        execution_sandbox = workspace_root / "sandbox"
        try:
            cls._copy_directory_contents(logical_sandbox, execution_sandbox)
        except Exception:
            # Allocation has succeeded, but the external copy is still only
            # ephemeral setup.  Do not leak it if snapshotting rejects a link
            # or encounters an I/O error before the Registry START boundary.
            shutil.rmtree(workspace_root, ignore_errors=True)
            raise
        return workspace_root, execution_sandbox

    @staticmethod
    def _resolve_executable(command: str, sandbox: Path, environment: dict[str, str]) -> str | None:
        candidate = Path(command)
        if candidate.is_absolute() and candidate.is_file():
            return str(candidate.resolve())
        sandbox_candidate = sandbox / candidate
        if sandbox_candidate.is_file():
            return str(sandbox_candidate.resolve())
        return shutil.which(command, path=environment.get("PATH"))

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Run one request and remove its short-lived workspace on every exit.

        The logical attempt remains in the project as auditable evidence.  The
        short external workspace is not evidence and must be removed even
        when an unexpected post-START operation (for example a snapshot,
        mirror or log write) raises before the normal registration cleanup.
        The holder is call-local, so concurrent calls do not share cleanup
        state.
        """
        workspace_holder: list[Path | None] = [None]
        try:
            return self._execute(request, workspace_holder)
        finally:
            workspace = workspace_holder[0]
            if workspace is not None:
                shutil.rmtree(workspace, ignore_errors=True)
                workspace_holder[0] = None

    def _execute(
        self,
        request: ExecutionRequest,
        workspace_holder: list[Path | None],
    ) -> ExecutionResult:
        if request.artifact_class not in {"production", "exploratory", "demo", "fixture"}:
            raise ConfigError("runner artifact_class is invalid")
        if not request.command or not all(isinstance(item, str) and item for item in request.command):
            raise ConfigError("execution requires a non-empty argument list")
        if not isinstance(request.timeout_seconds, int) or request.timeout_seconds <= 0:
            raise ConfigError("execution timeout must be a positive integer")
        if not isinstance(request.random_protocol, dict):
            raise ConfigError("random_protocol must be an object")
        outputs_contract, policies = self._comparison_contract(request)
        for argument in request.command[1:]:
            candidate = Path(argument)
            if candidate.is_absolute() and (
                candidate == self.project_root or self.project_root in candidate.parents
            ):
                raise UntrustedArtifactError(
                    "project files must execute from the sandbox snapshot, not their original path"
                )
            if ".." in candidate.parts:
                raise UntrustedArtifactError("command argument may not traverse out of sandbox")

        attempt_id = "attempt_" + uuid.uuid4().hex
        execution_id = "exec_" + uuid.uuid4().hex
        attempt_relative = Path("runs") / self.run_id / "attempts" / attempt_id
        attempt = resolve_within(
            self.project_root, self.project_root / attempt_relative, must_exist=False
        )
        if attempt.exists():
            raise IntegrityError("attempt directory already exists")
        # ``sandbox`` is the logical, auditable evidence location.  A second
        # short-lived workspace is used only as the child process cwd because
        # Windows CreateProcess rejects deeply nested paths near MAX_PATH.
        sandbox = attempt / "sandbox"
        output_dir = sandbox / "outputs"
        execution_workspace: Path | None = None

        def _remove_external_workspace() -> None:
            nonlocal execution_workspace
            if execution_workspace is not None:
                shutil.rmtree(execution_workspace, ignore_errors=True)
                execution_workspace = None
            workspace_holder[0] = None

        try:
            output_dir.mkdir(parents=True)
            snapshots = self._copy_sources(request, sandbox)
            self._verify_source_artifacts(request, snapshots)
            execution_workspace, process_sandbox = self._short_execution_workspace(sandbox)
            workspace_holder[0] = execution_workspace
            process_output_dir = process_sandbox / "outputs"
            environment = self._safe_environment(
                request, process_output_dir, cache_root=attempt / "runtime-cache"
            )
        except Exception:
            # Setup failures occur before any Registry evidence exists; the
            # short workspace is never admissible evidence and must vanish.
            _remove_external_workspace()
            raise
        # The producer receives immutable identity values so sidecars and
        # other structured outputs can bind themselves to this exact
        # execution without a post-hoc file mutation.
        environment.update(
            {
                "MMFLOW_EXECUTION_ID": execution_id,
                "MMFLOW_ATTEMPT_ID": attempt_id,
                "MMFLOW_RUN_ID": self.run_id,
            }
        )
        resolved_executable = self._resolve_executable(
            request.command[0], process_sandbox, environment
        )
        executable_sha256 = "0" * 64
        if resolved_executable is not None:
            try:
                executable_sha256 = sha256_file(resolved_executable)
            except OSError:
                executable_sha256 = "0" * 64
        code_snapshots = [item for item in snapshots if item.get("role") == "code"]
        source_imports = self._source_imports(self.project_root, code_snapshots)
        environment_lock = self._environment_lock()

        sandbox_before = self._snapshot_files(process_sandbox)
        # Record a canonical environment: the child's real MMFLOW_OUTPUT_DIR
        # lives in an ephemeral short-path workspace whose absolute location
        # is host-specific and disappears after the run.  Recording it verbatim
        # made identical runs produce byte-different ledger events and bloated
        # the immutable log, while adding zero forensic value (outputs are
        # mirrored back into the attempt directory and hashed there).  The
        # spawned child still receives the true path via `environment`.
        recorded_environment = dict(environment)
        if "MMFLOW_OUTPUT_DIR" in recorded_environment:
            recorded_environment["MMFLOW_OUTPUT_DIR"] = "@SANDBOX_OUTPUTS"
        intent: dict[str, Any] = {
            "execution_id": execution_id,
            "run_id": self.run_id,
            "attempt_id": attempt_id,
            "attempt_path": attempt_relative.as_posix(),
            "stage": request.stage,
            "question": request.question,
            "role": request.role,
            "artifact_class": request.artifact_class,
            "command": list(request.command),
            "working_directory": (attempt_relative / "sandbox").as_posix(),
            "resolved_executable": resolved_executable,
            "executable_sha256": executable_sha256,
            "environment_lock": environment_lock,
            "source_imports": source_imports,
            "source_snapshots": snapshots,
            "source_artifact_ids": list(request.source_artifact_ids),
            "dataset_split_ids": list(request.dataset_split_ids),
            "random_protocol": dict(request.random_protocol),
            "expected_outputs": outputs_contract,
            "comparison_policies": policies,
            "timeout_seconds": request.timeout_seconds,
            "requested_output_encoding": request.output_encoding,
            "environment": recorded_environment,
            "platform": platform.platform(),
            "python_version": sys.version,
            "policy_sha256": self.ledger.policy_sha256,
        }
        try:
            self.registry.start_execution(intent, stage=request.stage)
        except Exception:
            _remove_external_workspace()
            raise
        # The START event itself is an expected ledger mutation.  Establish the
        # external-project baseline after it so the attestation does not mark
        # its own immutable audit trail as an unauthorized model write.
        project_before = self._project_snapshot(attempt)
        started_at = datetime.now(timezone.utc)
        monotonic_started = time.monotonic()
        timed_out = False
        interrupted = False
        launch_error: str | None = None
        exit_code: int | None = None
        stdout_raw = b""
        stderr_raw = b""
        try:
            process = subprocess.Popen(
                request.command,
                cwd=process_sandbox,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
                start_new_session=os.name != "nt",
            )
        except OSError as error:
            launch_error = f"{type(error).__name__}: {error}"
            stderr_raw = launch_error.encode("utf-8", errors="replace")
            process = None
        if process is not None:
            try:
                stdout_raw, stderr_raw = process.communicate(
                    timeout=request.timeout_seconds
                )
                exit_code = int(process.returncode)
            except subprocess.TimeoutExpired as error:
                timed_out = True
                stdout_raw = error.stdout or b""
                stderr_raw = error.stderr or b""
                self._terminate_process_tree(process.pid)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
            except KeyboardInterrupt:
                interrupted = True
                self._terminate_process_tree(process.pid)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass

        finished_at = datetime.now(timezone.utc)
        duration_seconds = max(0.0, time.monotonic() - monotonic_started)
        sandbox_after = self._snapshot_files(process_sandbox)
        # Mirror the process workspace into the logical attempt only after the
        # child has exited.  This preserves the existing Registry path and
        # artifact lineage while keeping launch-time paths short.
        shutil.rmtree(sandbox, ignore_errors=True)
        self._copy_directory_contents(process_sandbox, sandbox)
        project_after = self._project_snapshot(attempt, previous=project_before)
        sandbox_created, sandbox_modified, sandbox_deleted = self._diff_snapshots(
            sandbox_before, sandbox_after
        )
        project_created, project_modified, project_deleted = self._diff_snapshots(
            project_before, project_after
        )

        atomic_write_bytes(attempt / "stdout.raw", stdout_raw)
        atomic_write_bytes(attempt / "stderr.raw", stderr_raw)
        stdout_text, stdout_meta = self._decode_log(stdout_raw, request.output_encoding)
        stderr_text, stderr_meta = self._decode_log(stderr_raw, request.output_encoding)
        atomic_write_bytes(attempt / "stdout.txt", stdout_text.encode("utf-8"))
        atomic_write_bytes(attempt / "stderr.txt", stderr_text.encode("utf-8"))

        # Sync outputs from short-path workspace back to logical sandbox.
        # Without this, files written to MMFLOW_OUTPUT_DIR during execution
        # are lost when the workspace is cleaned up.
        if process_output_dir.exists():
            for f in process_output_dir.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(process_output_dir)
                    dest = output_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)

        output_files = sorted(path for path in output_dir.rglob("*") if path.is_file())
        unsafe_outputs = [
            path.relative_to(output_dir).as_posix()
            for path in output_files
            if self._is_link_or_junction(path, output_dir)
        ]
        observed_outputs = [path.relative_to(output_dir).as_posix() for path in output_files]
        missing_outputs = sorted(set(outputs_contract) - set(observed_outputs))
        unexpected_outputs = sorted(set(observed_outputs) - set(outputs_contract))
        outside_sandbox_outputs = sorted(
            path for path in sandbox_created if not path.startswith("outputs/")
        )
        external_changes = [
            *(f"project-created:{path}" for path in project_created),
            *(f"project-modified:{path}" for path in project_modified),
            *(f"project-deleted:{path}" for path in project_deleted),
        ]
        unexpected_outside = sorted([*outside_sandbox_outputs, *external_changes])
        modified_files = sorted(sandbox_modified)
        deleted_files = sorted(sandbox_deleted)
        created_files = sorted(
            path[len("outputs/") :]
            for path in sandbox_created
            if path.startswith("outputs/")
        )
        valid = (
            exit_code == 0
            and not timed_out
            and not interrupted
            and launch_error is None
            and not missing_outputs
            and not unexpected_outputs
            and not unexpected_outside
            and not modified_files
            and not deleted_files
            and not unsafe_outputs
            and set(outputs_contract) == set(observed_outputs)
        )

        def _minimal_fix_hints() -> list[str]:
            """把四类高频违约翻译成一次可执行的最小修复建议。

            数据在上方清单里都已齐备；缺的只是组装——没有 hints 时 AI
            通常要人肉比对 1-2 轮才能配平输出卫生契约。
            """
            hints: list[str] = []
            for name in unexpected_outside:
                if name.startswith(("project-created:", "project-modified:", "project-deleted:")):
                    change_kind, changed = name.split(":", 1)
                    verb = {
                        "project-created": "创建",
                        "project-modified": "修改",
                        "project-deleted": "删除",
                    }[change_kind]
                    hints.append(
                        f"程序在 outputs/ 之外{verb}了 {changed}："
                        f"改为只写 MMFLOW_OUTPUT_DIR 指向的 outputs/ 目录"
                    )
                else:
                    hints.append(
                        f"沙箱根下出现意外文件 {name}：让程序把它写进 outputs/，"
                        f"或调整命令使其不产生该副产物（如 LaTeX 的 .aux/.log/.toc 需 "
                        f"-output-directory=outputs 或加入 expected_outputs）"
                    )
            for name in missing_outputs:
                hints.append(f"缺少声明输出 {name}：确认程序写出该文件到 outputs/，"
                             f"或从 expected_outputs 中移除并回退修订冻结计划")
            for name in unexpected_outputs:
                policy_missing = [
                    p for p in policies if p.get("output") == name
                ]
                if not policy_missing and request.artifact_class == "production":
                    hints.append(
                        f"多产出 {name}：要么加入 expected_outputs 并为其登记冻结比较策略，要么阻止程序生成它"
                    )
                else:
                    hints.append(f"多产出 {name}：阻止程序生成，或纳入 expected_outputs")
            for name in unsafe_outputs:
                hints.append(f"输出 {name} 是符号链接/junction：输出必须是普通文件")
            if modified_files or deleted_files:
                hints.append(
                    f"sandbox 内输入被改写/删除：{sorted([*modified_files, *deleted_files])[:8]} ——"
                    f"程序必须只读消费 inputs/，派生文件写入 outputs/"
                )
            if exit_code != 0 and not timed_out and launch_error is None:
                hints.append("非零退出码：先读 stderr.txt 定位实现层错误（见 SKILL.md 失败诊断树）")
            return hints

        execution_payload: dict[str, Any] = {
            "execution_id": execution_id,
            "run_id": self.run_id,
            "attempt_id": attempt_id,
            "attempt_path": attempt_relative.as_posix(),
            "stage": request.stage,
            "question": request.question,
            "role": request.role,
            "artifact_class": request.artifact_class,
            "command": list(request.command),
            "working_directory": (attempt_relative / "sandbox").as_posix(),
            "resolved_executable": resolved_executable,
            "executable_sha256": executable_sha256,
            "environment_lock": environment_lock,
            "source_imports": source_imports,
            "source_snapshots": snapshots,
            "source_artifact_ids": list(request.source_artifact_ids),
            "dataset_split_ids": list(request.dataset_split_ids),
            "random_protocol": dict(request.random_protocol),
            "expected_outputs": outputs_contract,
            "comparison_policies": policies,
            "observed_outputs": observed_outputs,
            "unexpected_outputs": unexpected_outputs,
            "unexpected_outside_outputs": unexpected_outside,
            "missing_outputs": missing_outputs,
            "unsafe_outputs": unsafe_outputs,
            "created_files": created_files,
            "modified_files": modified_files,
            "deleted_files": deleted_files,
            "timed_out": timed_out,
            "interrupted": interrupted,
            "launch_error": launch_error,
            "exit_code": exit_code,
            "stdout_raw_path": (attempt_relative / "stdout.raw").as_posix(),
            "stderr_raw_path": (attempt_relative / "stderr.raw").as_posix(),
            "stdout_raw_sha256": sha256_bytes(stdout_raw),
            "stderr_raw_sha256": sha256_bytes(stderr_raw),
            "stdout_decode": stdout_meta,
            "stderr_decode": stderr_meta,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": duration_seconds,
            "environment": recorded_environment,
            "platform": platform.platform(),
            "python_version": sys.version,
            "policy_sha256": self.ledger.policy_sha256,
            "timeout_seconds": request.timeout_seconds,
            "requested_output_encoding": request.output_encoding,
            "minimal_fix_hints": [] if valid else _minimal_fix_hints(),
            "intent_sha256": "",
            "status": "VALID" if valid else "INVALID",
        }
        from .registry import execution_intent_sha256

        execution_payload["intent_sha256"] = execution_intent_sha256(execution_payload)
        try:
            execution = self.registry.attest_execution(execution_payload)
        except Exception:
            _remove_external_workspace()
            raise
        artifacts: list[dict[str, Any]] = []
        try:
            if valid:
                for output in output_files:
                    logical = output.relative_to(output_dir).as_posix()
                    artifact_id = (
                        f"art_{execution_id}_{sha256_bytes(logical.encode('utf-8'))[:16]}"
                    )
                    media_type = mimetypes.guess_type(output.name)[0] or "application/octet-stream"
                    artifacts.append(
                        self.registry.register(
                            "artifact",
                            {
                                "artifact_id": artifact_id,
                                "run_id": self.run_id,
                                "artifact_class": request.artifact_class,
                                "artifact_type": "execution_output",
                                "status": "VALID",
                                "execution_id": execution_id,
                                "attempt_id": attempt_id,
                                "relative_path": output.relative_to(self.project_root).as_posix(),
                                "logical_output_path": logical,
                                "sha256": sha256_file(output),
                                "size_bytes": output.stat().st_size,
                                "media_type": media_type,
                                "inputs": list(request.source_artifact_ids),
                            },
                            stage=request.stage,
                        )
                    )
        finally:
            _remove_external_workspace()
        return ExecutionResult(execution=execution, artifacts=artifacts)

    def verify_artifact(self, artifact_id: str) -> bool:
        artifact = self.registry.latest("artifact", artifact_id)["payload"]
        path = resolve_within(
            self.project_root,
            self.project_root / artifact["relative_path"],
            must_exist=True,
        )
        if self._is_link_or_junction(path, self.project_root) or sha256_file(path) != artifact[
            "sha256"
        ]:
            raise IntegrityError(f"artifact changed after registration: {artifact_id}")
        execution_id = artifact.get("execution_id")
        if artifact.get("artifact_class") == "production":
            execution = self.registry.latest("execution", execution_id)["payload"]
            if execution["status"] != "VALID" or execution["exit_code"] != 0:
                raise IntegrityError("artifact producer execution is not valid")
        return True

    def reproduce(self, execution_id: str) -> ExecutionResult:
        original = self.registry.latest("execution", execution_id)["payload"]
        for snapshot in original["source_snapshots"]:
            source = self._source(
                snapshot["relative_path"], original["artifact_class"] == "production"
            )
            if sha256_file(source) != snapshot["sha256"]:
                raise IntegrityError("cannot reproduce: source snapshot changed")
        request = ExecutionRequest(
            stage="P9",
            question=original["question"],
            role=f"reproduce:{original['role']}",
            artifact_class=original["artifact_class"],
            command=list(original["command"]),
            input_paths=[
                item["relative_path"]
                for item in original["source_snapshots"]
                if item["role"] == "input"
            ],
            code_paths=[
                item["relative_path"]
                for item in original["source_snapshots"]
                if item["role"] == "code"
            ],
            config_paths=[
                item["relative_path"]
                for item in original["source_snapshots"]
                if item["role"] == "config"
            ],
            source_artifact_ids=list(original["source_artifact_ids"]),
            expected_outputs=list(original["expected_outputs"]),
            comparison_policies=dict(original["comparison_policies"]),
            dataset_split_ids=list(original["dataset_split_ids"]),
            random_protocol=dict(original["random_protocol"]),
            timeout_seconds=int(original["timeout_seconds"]),
            output_encoding=original.get("stdout_decode", {}).get("encoding"),
            environment={
                key: value
                for key, value in original.get("environment", {}).items()
                if not key.startswith("MMFLOW_")
                and key
                not in {
                    "PYTHONUTF8",
                    "PYTHONHASHSEED",
                    "PYTHONDONTWRITEBYTECODE",
                    "PYTHONPYCACHEPREFIX",
                    "TEMP",
                    "TMP",
                    "TMPDIR",
                    "MYPY_CACHE_DIR",
                    "RUFF_CACHE_DIR",
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
                    "PYTEST_ADDOPTS",
                }
            },
        )
        return self.execute(request)

    @staticmethod
    def _numeric_leaves(value: Any) -> list[float]:
        if isinstance(value, bool):
            return []
        if isinstance(value, (int, float)):
            if math.isfinite(float(value)):
                return [float(value)]
            return []
        if isinstance(value, dict):
            leaves: list[float] = []
            for child in value.values():
                leaves.extend(ExecutionRunner._numeric_leaves(child))
            return leaves
        if isinstance(value, list):
            leaves = []
            for child in value:
                leaves.extend(ExecutionRunner._numeric_leaves(child))
            return leaves
        return []

    @staticmethod
    def _statistic(values: list[float], statistic: str) -> float:
        if not values:
            raise ValueError("statistical comparison needs numeric samples")
        if statistic == "mean":
            return sum(values) / len(values)
        if statistic == "median":
            ordered = sorted(values)
            middle = len(ordered) // 2
            if len(ordered) % 2:
                return ordered[middle]
            return (ordered[middle - 1] + ordered[middle]) / 2.0
        if statistic == "max_abs":
            return max(abs(value) for value in values)
        raise ValueError(f"unknown statistic: {statistic}")

    @staticmethod
    def _compare_statistical_json(
        left: Any,
        right: Any,
        policy: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        left_values = ExecutionRunner._numeric_leaves(left)
        right_values = ExecutionRunner._numeric_leaves(right)
        statistic = str(policy.get("statistic", "mean"))
        left_stat = ExecutionRunner._statistic(left_values, statistic)
        right_stat = ExecutionRunner._statistic(right_values, statistic)
        absolute = float(policy.get("absolute_tolerance", 0.0))
        relative = float(policy.get("relative_tolerance", 0.0))
        scale = max(abs(left_stat), abs(right_stat))
        equal = abs(left_stat - right_stat) <= max(absolute, relative * scale)
        return equal, {
            "statistic": statistic,
            "left": left_stat,
            "right": right_stat,
            "n_left": len(left_values),
            "n_right": len(right_values),
            "confidence_level": policy.get("confidence_level"),
            "min_sample_size": policy.get("min_sample_size"),
            "n_seeds": policy.get("n_seeds"),
        }

    @staticmethod
    def _compare_numeric_json(
        left: Any, right: Any, absolute: float, relative: float
    ) -> bool:
        if isinstance(left, bool) or isinstance(right, bool):
            return left is right
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if not math.isfinite(float(left)) or not math.isfinite(float(right)):
                return False
            difference = abs(float(left) - float(right))
            scale = max(abs(float(left)), abs(float(right)))
            return difference <= max(absolute, relative * scale)
        if type(left) is not type(right):
            return False
        if isinstance(left, dict):
            return set(left) == set(right) and all(
                ExecutionRunner._compare_numeric_json(
                    left[key], right[key], absolute, relative
                )
                for key in left
            )
        if isinstance(left, list):
            return len(left) == len(right) and all(
                ExecutionRunner._compare_numeric_json(a, b, absolute, relative)
                for a, b in zip(left, right)
            )
        return left == right

    def compare_reproduction(
        self, original_execution_id: str, reproduction: ExecutionResult
    ) -> dict[str, Any]:
        original_execution = self.registry.latest(
            "execution", original_execution_id
        )["payload"]
        reproduction_id = reproduction.execution["entity_id"]
        original_artifacts = {
            record["payload"]["logical_output_path"]: record["payload"]
            for record in self.registry.iter_latest("artifact")
            if record["payload"].get("execution_id") == original_execution_id
        }
        reproduced_artifacts = {
            record["payload"]["logical_output_path"]: record["payload"]
            for record in self.registry.iter_latest("artifact")
            if record["payload"].get("execution_id") == reproduction_id
        }
        checks: list[dict[str, Any]] = []
        all_paths = sorted(set(original_artifacts) | set(reproduced_artifacts))
        policies = original_execution["comparison_policies"]
        for logical_path in all_paths:
            left = original_artifacts.get(logical_path)
            right = reproduced_artifacts.get(logical_path)
            policy = policies.get(logical_path)
            if left is None or right is None or not isinstance(policy, dict):
                checks.append(
                    {
                        "logical_path": logical_path,
                        "mode": None,
                        "status": "FAIL",
                        "reason": "missing output or frozen policy",
                    }
                )
                continue
            mode = policy.get("mode")
            equal = False
            statistical_detail: dict[str, Any] | None = None
            if mode == "sha256":
                equal = left["sha256"] == right["sha256"]
            elif mode in {"json_exact", "json_numeric", "statistical_json"}:
                try:
                    left_value = json.loads(
                        (self.project_root / left["relative_path"]).read_text("utf-8")
                    )
                    right_value = json.loads(
                        (self.project_root / right["relative_path"]).read_text("utf-8")
                    )
                except (OSError, UnicodeError, json.JSONDecodeError) as error:
                    checks.append(
                        {
                            "logical_path": logical_path,
                            "mode": mode,
                            "status": "ERROR",
                            "reason": f"cannot parse JSON: {type(error).__name__}",
                        }
                    )
                    continue
                if mode == "json_exact":
                    equal = left_value == right_value
                elif mode == "json_numeric":
                    equal = self._compare_numeric_json(
                        left_value,
                        right_value,
                        float(policy["absolute_tolerance"]),
                        float(policy["relative_tolerance"]),
                    )
                else:
                    try:
                        equal, statistical_detail = self._compare_statistical_json(
                            left_value, right_value, policy
                        )
                    except ValueError as error:
                        checks.append(
                            {
                                "logical_path": logical_path,
                                "mode": mode,
                                "status": "ERROR",
                                "reason": str(error),
                            }
                        )
                        continue
            else:
                checks.append(
                    {
                        "logical_path": logical_path,
                        "mode": mode,
                        "status": "ERROR",
                        "reason": "unsupported frozen policy",
                    }
                )
                continue
            check = {
                "logical_path": logical_path,
                "mode": mode,
                "status": "PASS" if equal else "FAIL",
                "reason": f"comparison mode {mode}",
            }
            if statistical_detail is not None:
                check["statistical_detail"] = statistical_detail
            checks.append(check)
        reproduction_payload = self.registry.latest(
            "execution", reproduction_id
        )["payload"]
        conditions: dict[str, Any] = {}
        for field in ("timeout_seconds", "platform", "python_version", "resolved_executable"):
            original_value = original_execution.get(field)
            reproduced_value = reproduction_payload.get(field)
            if original_value != reproduced_value:
                conditions[field] = {
                    "original": original_value,
                    "reproduced": reproduced_value,
                    "status": "DIFF",
                }
        if int(original_execution["timeout_seconds"]) != int(
            reproduction_payload["timeout_seconds"]
        ):
            conditions["timeout_seconds"] = {
                "original": original_execution["timeout_seconds"],
                "reproduced": reproduction_payload["timeout_seconds"],
                "status": "FAIL",
            }
        outcome = (
            "PASS"
            if checks
            and all(check["status"] == "PASS" for check in checks)
            and all(
                condition.get("status") != "FAIL"
                for condition in conditions.values()
            )
            else "ERROR"
            if any(check["status"] == "ERROR" for check in checks)
            else "FAIL"
        )
        return {
            "report_version": 2,
            "outcome": outcome,
            "original_execution_id": original_execution_id,
            "reproduction_execution_id": reproduction_id,
            "checks": checks,
            "conditions": conditions,
        }
