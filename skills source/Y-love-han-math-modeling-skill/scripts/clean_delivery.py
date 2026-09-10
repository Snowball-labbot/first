"""One-command clean delivery closed loop for the integrated skill.

The orchestrator never writes into the source skill tree.  Every step runs on
a clean copy produced in a temporary directory:

1. ``build_release`` copy: caches, bytecode, ``.mmflow`` and VCS state are
   excluded; the copy is rescanned for forbidden members and hashed.
2. ``validate_skill`` runs against the clean copy.
3. ``integrate_templates check`` validates the template manifest in the copy.
4. Every ``.py`` file in the copy is parsed with ``ast`` (no bytecode is
   written) to prove syntax health.
5. Grouped tests run inside the copy via its own ``run_tests.py`` entry
   (``--tests quick`` by default, ``full`` for the exhaustive suite,
   ``skip`` for packaging-only runs).
6. A release ZIP is built from the clean copy and every member path is
   checked for traversal, absolute paths and forbidden content.
7. A JSON release report records each step as program facts only; quality,
   originality and prize judgments are never produced here.

On success the temporary clean copy is removed; on failure it is preserved
and its path is reported so the failure can be inspected.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
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
RELEASE_SCHEMA = "math-modeling-clean-delivery/v1"
ZIP_NAME = "math-modeling-release.zip"


class CleanDeliveryError(RuntimeError):
    """Raised when the delivery loop cannot even start safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_python(script: Path, args: list[str], cwd: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    run_root = Path(tempfile.mkdtemp(prefix="mmflow-step-"))
    env["PYTHONPYCACHEPREFIX"] = str(run_root / "pycache")
    env["TEMP"] = str(run_root / "tmp")
    env["TMP"] = str(run_root / "tmp")
    env["TMPDIR"] = str(run_root / "tmp")
    env["MYPY_CACHE_DIR"] = str(run_root / "mypy")
    env["RUFF_CACHE_DIR"] = str(run_root / "ruff")
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    Path(env["PYTHONPYCACHEPREFIX"]).mkdir(parents=True, exist_ok=True)
    Path(env["TEMP"]).mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, "-B", str(script), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    result = {
        "command": [str(script), *args],
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        # Keep the complete stream for callers that need structured progress
        # extraction.  ``stderr_tail`` remains the compact field used in
        # release reports so reports do not grow without bound.
        "stderr": completed.stderr,
        "stderr_tail": completed.stderr[-2000:],
    }
    shutil.rmtree(run_root, ignore_errors=True)
    return result


def _step_build_release(source: Path, clean_root: Path) -> dict[str, Any]:
    result = _run_python(
        SCRIPT_DIR / "build_release.py",
        ["--source", str(source), "--output", str(clean_root), "--json"],
        cwd=SCRIPT_DIR,
    )
    compact = {
        "command": result["command"],
        "returncode": result["returncode"],
        "stderr_tail": result["stderr_tail"],
    }
    if result["returncode"] != 0:
        return {"status": "FAIL", **compact}
    try:
        report = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {"status": "FAIL", "reason": "build_release report unparsable", **compact}
    if report.get("status") != "PASS" or report.get("forbidden_members"):
        return {
            "status": "FAIL",
            "reason": "build_release detected forbidden members",
            "forbidden_members": report.get("forbidden_members"),
            **compact,
        }
    return {
        "status": "PASS",
        "file_count": report.get("file_count"),
        "sha256": report.get("sha256"),
        **compact,
    }


def _step_syntax(clean_root: Path) -> dict[str, Any]:
    failures: list[str] = []
    count = 0
    for path in sorted(clean_root.rglob("*.py")):
        if any(part in EXCLUDED_DIRS for part in path.relative_to(clean_root).parts):
            continue
        count += 1
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError, OSError) as error:
            failures.append(f"{path.relative_to(clean_root)}: {error}")
    return {
        "status": "PASS" if not failures else "FAIL",
        "checked_files": count,
        "failures": failures,
    }


def _step_tests(clean_root: Path, mode: str) -> dict[str, Any]:
    if mode == "skip":
        return {"status": "SKIP", "mode": mode}
    args = ["--quick"] if mode == "quick" else ["--full"]
    args.extend(["--output-root", str(clean_root.parent / "test-runs")])
    result = _run_python(clean_root / "scripts" / "run_tests.py", args, cwd=clean_root)
    status = "PASS" if result["returncode"] == 0 else "FAIL"
    return {
        "status": status,
        "mode": mode,
        "command": result["command"],
        "returncode": result["returncode"],
        "stdout_tail": result["stdout"][-2000:],
        "stderr_tail": result["stderr_tail"],
        "progress": [
            line for line in result["stderr"].splitlines()
            if '"event"' in line
        ],
    }


def _zip_member_is_safe(name: str) -> bool:
    if not name or name.startswith("/") or name.startswith("\\"):
        return False
    parts = Path(name).parts
    if any(part in ("..", "") for part in parts):
        return False
    if any(part in EXCLUDED_DIRS for part in parts):
        return False
    suffix = Path(name).suffix.lower()
    if suffix in EXCLUDED_SUFFIXES:
        return False
    if Path(name).name in EXCLUDED_NAMES:
        return False
    return True


def _step_zip(clean_root: Path, output_dir: Path) -> dict[str, Any]:
    zip_path = output_dir / ZIP_NAME
    members: list[str] = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(clean_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(clean_root).as_posix()
            if not _zip_member_is_safe(relative):
                return {
                    "status": "FAIL",
                    "reason": f"unsafe member blocked before archiving: {relative}",
                }
            archive.write(path, arcname=relative)
            members.append(relative)
    # Verify from the archive itself, not from the build list.
    with zipfile.ZipFile(zip_path, "r") as archive:
        unsafe = [name for name in archive.namelist() if not _zip_member_is_safe(name)]
    if unsafe:
        return {"status": "FAIL", "reason": "archive contains unsafe members", "unsafe": unsafe}
    return {
        "status": "PASS",
        "zip_path": str(zip_path),
        "zip_sha256": _sha256(zip_path),
        "member_count": len(members),
    }


def run_clean_delivery(
    source: Path,
    output_dir: Path,
    *,
    tests_mode: str = "quick",
) -> dict[str, Any]:
    source = source.resolve()
    output_dir = output_dir.resolve()
    if not source.is_dir():
        raise CleanDeliveryError(f"source is not a directory: {source}")
    if not (source / "SKILL.md").is_file():
        raise CleanDeliveryError("source does not look like a skill root (missing SKILL.md)")
    if output_dir == source or output_dir.is_relative_to(source):
        raise CleanDeliveryError("output must not be the source or inside the source")
    if output_dir.exists():
        raise CleanDeliveryError(f"output already exists: {output_dir}")
    if os.environ.get("MMFLOW_CLEAN_DELIVERY_CHILD") == "1" and tests_mode == "full":
        # Never allow a nested delivery run to start the exhaustive suite;
        # that path exists only to avoid accidental recursive pytest trees.
        tests_mode = "skip"

    output_dir.mkdir(parents=True)
    clean_root = Path(tempfile.mkdtemp(prefix="mmflow-clean-")) / "skill"
    steps: dict[str, Any] = {}
    overall = "PASS"

    def record(name: str, result: dict[str, Any]) -> bool:
        nonlocal overall
        steps[name] = result
        if result.get("status") == "FAIL":
            overall = "FAIL"
            return False
        return True

    try:
        if not record("build_release", _step_build_release(source, clean_root)):
            return _report(source, output_dir, overall, steps, clean_root, preserved=True)
        validator_result = _run_python(
            clean_root / "scripts" / "validate_skill.py",
            ["--skill-root", str(clean_root), "--json"],
            cwd=clean_root,
        )
        if not record("validate_skill", _validated_step(validator_result)):
            return _report(source, output_dir, overall, steps, clean_root, preserved=True)
        manifest_check = _run_python(
            clean_root / "scripts" / "integrate_templates.py",
            ["check", "--root", str(clean_root), "--json"],
            cwd=clean_root,
        )
        if not record(
            "template_manifest",
            {
                **manifest_check,
                "stdout": manifest_check["stdout"][-2000:],
                "status": "PASS" if manifest_check["returncode"] == 0 else "FAIL",
            },
        ):
            return _report(source, output_dir, overall, steps, clean_root, preserved=True)
        if not record("syntax", _step_syntax(clean_root)):
            return _report(source, output_dir, overall, steps, clean_root, preserved=True)
        old_value = os.environ.get("MMFLOW_CLEAN_DELIVERY_CHILD")
        os.environ["MMFLOW_CLEAN_DELIVERY_CHILD"] = "1"
        try:
            if not record("tests", _step_tests(clean_root, tests_mode)):
                return _report(source, output_dir, overall, steps, clean_root, preserved=True)
        finally:
            if old_value is None:
                os.environ.pop("MMFLOW_CLEAN_DELIVERY_CHILD", None)
            else:
                os.environ["MMFLOW_CLEAN_DELIVERY_CHILD"] = old_value
        if not record("zip_safety", _step_zip(clean_root, output_dir)):
            return _report(source, output_dir, overall, steps, clean_root, preserved=True)
        return _report(source, output_dir, overall, steps, clean_root, preserved=False)
    except Exception:
        return _report(source, output_dir, "ERROR", steps, clean_root, preserved=True)


def _validated_step(result: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "command": result["command"],
        "returncode": result["returncode"],
        "stderr_tail": result["stderr_tail"],
        "stdout_tail": result["stdout"][-2000:],
    }
    if result["returncode"] != 0:
        return {**compact, "status": "FAIL"}
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {**compact, "status": "FAIL", "reason": "validator output unparsable"}
    if payload.get("status") != "PASS":
        failed = [item.get("rule_id") for item in payload.get("checks", []) if item.get("status") != "PASS"]
        return {**compact, "status": "FAIL", "failed_checks": failed}
    return {**compact, "status": "PASS", "checks": len(payload.get("checks", []))}


def _report(
    source: Path,
    output_dir: Path,
    status: str,
    steps: dict[str, Any],
    clean_root: Path,
    *,
    preserved: bool,
) -> dict[str, Any]:
    if status == "PASS" and not preserved:
        shutil.rmtree(clean_root.parent, ignore_errors=True)
        clean_root_reported = None
    else:
        clean_root_reported = str(clean_root)
    report = {
        "schema": RELEASE_SCHEMA,
        "status": status,
        "source": str(source),
        "output": str(output_dir),
        "clean_copy_preserved": clean_root_reported,
        "steps": steps,
        "disclosure": {
            "program_facts": [
                "file hashes",
                "validator and manifest results",
                "syntax results",
                "test return codes",
                "zip member safety",
            ],
            "not_covered": [
                "scientific quality of future projects",
                "originality",
                "judge acceptance or prize outcome",
            ],
        },
    }
    (output_dir / "release_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build, verify and package a clean skill delivery without touching the source tree"
    )
    parser.add_argument("--source", default=str(SKILL_ROOT))
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--tests",
        choices=("quick", "full", "skip"),
        default="quick",
        help="grouped tests to run inside the clean copy (default: quick)",
    )
    args = parser.parse_args(argv)
    try:
        report = run_clean_delivery(
            Path(args.source),
            Path(args.output),
            tests_mode=args.tests,
        )
    except CleanDeliveryError as error:
        print(json.dumps({"schema": RELEASE_SCHEMA, "status": "ERROR", "reason": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
