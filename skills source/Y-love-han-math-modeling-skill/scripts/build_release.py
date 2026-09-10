"""Build a clean, auditable copy of the skill without runtime state."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


EXCLUDED_DIRS = {
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".mmflow",
    ".git",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".bak", ".swp", ".swo"}
EXCLUDED_NAMES = {".coverage", ".coverage.sqlite"}


def _copy(source: Path, destination: Path) -> list[str]:
    included: list[str] = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            included.append(relative.as_posix())
    return included


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a clean math-modeling skill release copy")
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    if source == output or output.is_relative_to(source):
        raise SystemExit("output must not be the source or inside the source")
    if output.exists():
        raise SystemExit(f"output already exists: {output}")
    files = _copy(source, output)
    forbidden = [
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
        and (
            path.suffix.lower() in EXCLUDED_SUFFIXES
            or any(part in EXCLUDED_DIRS for part in path.relative_to(output).parts)
        )
    ]
    report = {
        "schema": "math-modeling-clean-release/v1",
        "status": "PASS" if not forbidden else "FAIL",
        "source": str(source),
        "output": str(output),
        "file_count": len(files),
        "forbidden_members": forbidden,
        "sha256": {relative: _sha256(output / relative) for relative in files},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not forbidden else 1


if __name__ == "__main__":
    raise SystemExit(main())
