from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, sha256_bytes, sha256_file
from .errors import IntegrityError


def runtime_policy_files(skill_root: Path | str) -> list[Path]:
    root = Path(skill_root).resolve()
    required_roots = [
        root / "SKILL.md",
        root / "scripts" / "mmflow.py",
        root / "scripts" / "mmflow_core",
        root / "references",
        root / "templates" / "production",
    ]
    missing = [path for path in required_roots if not path.exists()]
    if missing:
        raise IntegrityError(
            "missing runtime policy file: " + ", ".join(str(path) for path in missing)
        )
    files = [root / "SKILL.md", root / "scripts" / "__init__.py", root / "scripts" / "mmflow.py"]
    files.extend(sorted((root / "scripts" / "mmflow_core").rglob("*.py")))
    files.extend(sorted((root / "scripts" / "mmflow_core" / "policies").glob("*.json")))
    files.extend(sorted((root / "references").glob("*.md")))
    files.extend(sorted((root / "templates" / "production").rglob("*")))
    return sorted(
        {path for path in files if path.is_file()},
        key=lambda path: path.relative_to(root).as_posix(),
    )


def build_policy_lock(skill_root: Path | str) -> dict[str, Any]:
    root = Path(skill_root).resolve()
    files = {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in runtime_policy_files(root)
    }
    body: dict[str, Any] = {"lock_version": 1, "files": files}
    body["policy_sha256"] = sha256_bytes(canonical_json_bytes(body))
    return body


def verify_policy_lock(skill_root: Path | str, lock: dict[str, Any]) -> bool:
    expected_hash = lock.get("policy_sha256")
    body = {"lock_version": lock.get("lock_version"), "files": lock.get("files")}
    if expected_hash != sha256_bytes(canonical_json_bytes(body)):
        raise IntegrityError("policy lock self-hash mismatch")
    actual = build_policy_lock(skill_root)
    if actual["files"] != lock.get("files"):
        raise IntegrityError("runtime policy files changed")
    return True
