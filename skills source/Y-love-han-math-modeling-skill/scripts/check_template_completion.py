"""Check a concrete project delivery for unresolved template tokens.

The Skill itself may contain explicit skeleton tokens.  A copied project,
however, must either replace them or record a structured NOT_APPLICABLE
decision; this checker is intentionally pointed at the project delivery root,
not at the Skill template directory.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TEXT_SUFFIXES = {".md", ".py", ".json", ".tex", ".txt", ".yaml", ".yml", ".csv"}
TOKEN_PATTERNS = {
    "unfinished_marker": re.compile(r"(?i)\b(?:TODO|TBD|FIXME|XXX)\b"),
    "angle_fill": re.compile(r"(?i)<(?:fill|enter|replace|your|paper|team|problem|key|core|method|theory|contribution|algorithm|result|keyword|supported)[^>]*>"),
    "chinese_fill": re.compile(r"\[(?:在此|填写|替换|粘贴|待补|待定)[^\]]*\]"),
    "example_name": re.compile(r"(?i)\bexample_[A-Za-z0-9_.-]+"),
}
IGNORED_DIRS = {".git", ".mmflow", ".pytest_cache", "__pycache__"}


def scan_project(root: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    findings: list[dict[str, Any]] = []
    if not root.is_dir():
        return {"status": "FAIL", "root": str(root), "findings": [{"error": "root is not a directory"}]}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        try:
            lines = path.read_text("utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            findings.append({"path": path.relative_to(root).as_posix(), "error": str(error)})
            continue
        for line_number, line in enumerate(lines, start=1):
            for kind, pattern in TOKEN_PATTERNS.items():
                if pattern.search(line):
                    findings.append({
                        "path": path.relative_to(root).as_posix(),
                        "line": line_number,
                        "kind": kind,
                        "text": line.strip()[:240],
                    })
    return {
        "status": "PASS" if not findings else "FAIL",
        "root": str(root),
        "findings": findings,
        "checked_suffixes": sorted(TEXT_SUFFIXES),
        "policy": "delivery projects must replace skeleton tokens before final submission",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="check project template completion")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = scan_project(args.project_root)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else report["status"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
