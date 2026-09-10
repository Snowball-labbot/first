from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .errors import ConfigError, IntegrityError


def _validate_json_value(value: Any, location: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigError(f"non-finite float at {location}")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ConfigError(f"non-string JSON key at {location}")
            _validate_json_value(child, f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_json_value(child, f"{location}[{index}]")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ConfigError(f"unsupported JSON type {type(value).__name__} at {location}")


def canonical_json_bytes(value: Any) -> bytes:
    _validate_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    target = Path(path)
    _assert_no_reparse_ancestors(target.parent)
    if _is_reparse_point(target):
        raise IntegrityError(f"atomic-write target may not be a link or reparse point: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path | str, value: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value) + b"\n")


def _is_reparse_point(path: Path | str) -> bool:
    """Return whether *path* is a link or Windows reparse point.

    ``Path.resolve`` is not a security check: it follows links before the
    caller gets a chance to inspect them.  Keep this probe non-following and
    fail closed when the operating system will not let us inspect a path.
    """

    candidate = Path(path)
    try:
        if candidate.is_symlink():
            return True
    except OSError:
        return True
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction is not None:
        try:
            if is_junction(os.fspath(candidate)):
                return True
        except OSError:
            return True
    try:
        attributes = getattr(os.stat(candidate, follow_symlinks=False), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return bool(attributes & reparse_flag)


def _assert_no_reparse_ancestors(path: Path | str, stop: Path | str | None = None) -> None:
    """Reject links/reparse points in an existing parent chain.

    Missing leaf components are allowed; every existing component is checked.
    This is deliberately independent of ``resolve_within`` so internal
    atomic writes cannot silently follow a replaced directory.
    """

    current = Path(path)
    boundary = Path(stop).absolute() if stop is not None else None
    while True:
        if _is_reparse_point(current):
            raise IntegrityError(f"path component may not be a link or reparse point: {current}")
        if boundary is not None and current == boundary:
            return
        parent = current.parent
        if parent == current:
            return
        current = parent


def _lexical_absolute(path: Path | str) -> Path:
    """Normalize a path without resolving links."""

    return Path(os.path.abspath(os.fspath(Path(path))))


def _same_or_child(root: Path, candidate: Path) -> bool:
    try:
        common = os.path.commonpath((os.fspath(root), os.fspath(candidate)))
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(os.fspath(root))


def resolve_within(
    root: Path | str,
    candidate: Path | str,
    must_exist: bool = False,
) -> Path:
    try:
        resolved_root = Path(root).resolve(strict=True)
    except OSError as error:
        raise IntegrityError(f"allowed root is not accessible: {root}") from error
    if not resolved_root.is_dir() or _is_reparse_point(resolved_root):
        raise IntegrityError(f"allowed root must be a regular directory: {resolved_root}")

    requested = Path(candidate)
    lexical_root = _lexical_absolute(root)
    lexical_candidate = _lexical_absolute(
        requested if requested.is_absolute() else lexical_root / requested
    )
    if not _same_or_child(lexical_root, lexical_candidate):
        raise IntegrityError(f"path escapes allowed root: {lexical_candidate}")

    relative = lexical_candidate.relative_to(lexical_root)
    current = lexical_root
    if _is_reparse_point(current):
        raise IntegrityError(f"path component may not be a link or reparse point: {current}")
    for component in relative.parts:
        current = current / component
        if _is_reparse_point(current):
            raise IntegrityError(f"path component may not be a link or reparse point: {current}")

    try:
        resolved_candidate = lexical_candidate.resolve(strict=must_exist)
    except OSError as error:
        raise IntegrityError(f"path cannot be resolved safely: {lexical_candidate}") from error
    if not _same_or_child(resolved_root, resolved_candidate):
        raise IntegrityError(f"path escapes allowed root: {resolved_candidate}")
    # Recheck the resolved path as a defense against a reparse point appearing
    # between the lexical inspection and the OS resolution call.
    _assert_no_reparse_ancestors(resolved_candidate, resolved_root)
    return resolved_candidate


def resolve_regular_file_within(
    root: Path | str,
    candidate: Path | str,
) -> Path:
    root_path = Path(root)
    requested = Path(candidate)
    anchored = requested if requested.is_absolute() else root_path / requested
    try:
        resolved = resolve_within(root_path, anchored, must_exist=True)
    except OSError as error:
        raise IntegrityError(f"project input does not exist: {anchored}") from error
    if not resolved.is_file() or _is_reparse_point(resolved):
        raise IntegrityError(f"project input is not a regular file: {resolved}")
    return resolved


def is_reparse_point(path: Path | str) -> bool:
    """Public non-following link/reparse probe for registry and runner checks."""

    return _is_reparse_point(path)


def path_chain_has_reparse(
    path: Path | str, root: Path | str
) -> bool:
    """Return whether an existing path component up to *root* is unsafe."""

    current = Path(path)
    boundary = Path(root).absolute()
    while True:
        if _is_reparse_point(current):
            return True
        if current == boundary:
            return False
        if boundary not in current.parents:
            return True
        current = current.parent


def normalize_relative_posix(raw: Any, *, field: str = "path") -> str:
    """Validate and normalize a project-relative POSIX path."""

    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise IntegrityError(f"{field} must be a non-empty POSIX relative path")
    logical = Path(raw)
    if logical.is_absolute() or ".." in logical.parts or "." in logical.parts:
        raise IntegrityError(f"{field} must be a normalized relative path")
    normalized = logical.as_posix()
    if normalized != raw:
        raise IntegrityError(f"{field} is not canonically normalized")
    return normalized
