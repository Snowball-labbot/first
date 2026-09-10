from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


REFERENCE_NAMES = (
    "workflow-contract.md",
    "problem-formalization.md",
    "model-selection.md",
    "validation-by-model-type.md",
    "data-and-literature-governance.md",
    "evidence-and-claims.md",
    "competition-compliance.md",
    "paper-and-visuals.md",
    "review-recovery-and-defense.md",
)
EXTENDED_REFERENCE_NAMES = (
    "extended-competition-playbook.md",
    "extended-sprint-protocol.md",
)
POLICY_ROOTS = (
    "SKILL.md",
    "references",
    "templates/production",
    "templates/analytics",
    "templates/publication",
    "templates/presentation",
    "templates/quality",
    "templates/visualization",
    "agents",
)
RUNTIME_LINK_ROOTS = (
    "SKILL.md",
    "scripts/mmflow.py",
    "scripts/mmflow_core",
    "references",
    "templates/production",
    "templates/visualization",
    "agents",
)
FIXED_QUOTAS = (
    "至少12张3D",
    "至少 12 张 3D",
    "每问至少6张图",
    "每问至少 6 张图",
    "正文必须28",
    "正文必须 28",
    "摘要必须撑满",
    "固定10折",
    "固定 10 折",
    "每问至少3个创新",
    "每问至少 3 个创新",
)
AWARD_GUARANTEES = (
    "保证获得特等奖",
    "确保获得特等奖",
    "保证获奖",
    "必然获奖",
)
PLACEHOLDERS = re.compile(
    r"(?im)\b(?:TODO|TBD|FIXME|XXX)\b|待定|待补|类似 Task \d+"
)
TEXT_SUFFIXES = {".md", ".py", ".json", ".tex", ".yaml", ".yml"}
ARCHIVE_PATH = re.compile(r"(?i)workspace\.legacy|(?<![A-Za-z])legacy[\\/]")
NEGATION_CONTEXT = re.compile(
    r"(?:不得|不能|不可|不应|禁止|并非|不是|无法|不保证|勿|严禁)"
)
PLACEHOLDER_AUDIT_CONTEXT = re.compile(
    r"(?:扫描|审计|检测|查找|拒绝|禁止|不得|清除|未完成标记|占位审计|示例|模板|占位符|伪代码|命令示例|变量占位)"
)


def split_frontmatter(text: str) -> tuple[list[str], str]:
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("SKILL.md frontmatter is not closed")
    keys: list[str] = []
    for line in text[4:end].splitlines():
        if line and not line.startswith((" ", "\t")) and ":" in line:
            keys.append(line.split(":", 1)[0].strip())
    return keys, text[end + 5 :]


def check(rule_id: str, condition: bool, reason: str) -> dict[str, str]:
    return {
        "rule_id": rule_id,
        "status": "PASS" if condition else "FAIL",
        "reason": reason,
    }


def parse_openai_yaml(path: Path) -> tuple[set[str], dict[str, str]]:
    lines = path.read_text("utf-8").splitlines()
    if not lines or lines[0] != "interface:":
        raise ValueError("agents/openai.yaml must contain only an interface root")
    keys: set[str] = set()
    values: dict[str, str] = {}
    for line in lines[1:]:
        if not line.startswith("  ") or ":" not in line:
            raise ValueError("invalid or unexpected top-level agents metadata")
        key, value = line.strip().split(":", 1)
        if key in keys:
            raise ValueError(f"duplicate agents metadata key: {key}")
        keys.add(key)
        values[key] = value.strip().strip('"')
    return keys, values


def _collect_text(root: Path, roots: tuple[str, ...]) -> str:
    collected: list[str] = []
    for relative in roots:
        path = root / relative
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = sorted(item for item in path.rglob("*") if item.is_file())
        else:
            continue
        for file in files:
            if file.suffix.lower() in TEXT_SUFFIXES:
                collected.append(file.read_text("utf-8", errors="replace"))
    return "\n".join(collected)


def _iter_text_files(root: Path, roots: tuple[str, ...]):
    seen: set[Path] = set()
    for relative in roots:
        path = root / relative
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = sorted(item for item in path.rglob("*") if item.is_file())
        else:
            continue
        for file in files:
            resolved = file.resolve()
            if resolved in seen or file.suffix.lower() not in TEXT_SUFFIXES:
                continue
            seen.add(resolved)
            yield file


def _archive_runtime_findings(root: Path) -> list[str]:
    findings: list[str] = []
    for file in _iter_text_files(root, RUNTIME_LINK_ROOTS):
        lines = file.read_text("utf-8", errors="replace").splitlines()
        exclusion_tuple = False
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if file.suffix.lower() == ".py" and re.match(
                r"^[A-Z0-9_]*(?:FORBIDDEN|EXCLUDED|OMITTED|DENIED)[A-Z0-9_]*\s*=\s*\(",
                stripped,
            ):
                exclusion_tuple = True
            matches = ARCHIVE_PATH.search(line)
            if matches and not exclusion_tuple:
                findings.append(
                    f"{file.relative_to(root).as_posix()}:{line_number}"
                )
            if exclusion_tuple and ")" in stripped:
                exclusion_tuple = False
    return findings


def _award_guarantee_findings(root: Path) -> list[str]:
    findings: list[str] = []
    for file in _iter_text_files(root, POLICY_ROOTS):
        for line_number, line in enumerate(
            file.read_text("utf-8", errors="replace").splitlines(), start=1
        ):
            for phrase in AWARD_GUARANTEES:
                position = line.find(phrase)
                if position < 0:
                    continue
                prefix = line[max(0, position - 96) : position]
                if NEGATION_CONTEXT.search(prefix):
                    continue
                findings.append(
                    f"{file.relative_to(root).as_posix()}:{line_number}"
                )
    return findings


def _placeholder_findings(root: Path) -> list[str]:
    findings: list[str] = []
    for file in _iter_text_files(root, POLICY_ROOTS):
        for line_number, line in enumerate(
            file.read_text("utf-8", errors="replace").splitlines(), start=1
        ):
            match = PLACEHOLDERS.search(line)
            if match is None:
                continue
            prefix = line[max(0, match.start() - 96) : match.start()]
            if PLACEHOLDER_AUDIT_CONTEXT.search(prefix):
                continue
            findings.append(f"{file.relative_to(root).as_posix()}:{line_number}")
    return findings


def validate_skill_root(skill_root: Path | str) -> dict[str, Any]:
    root = Path(skill_root).resolve()
    checks: list[dict[str, str]] = []
    try:
        skill_text = (root / "SKILL.md").read_text("utf-8")
        keys, body = split_frontmatter(skill_text)
    except Exception as error:
        return {
            "status": "FAIL",
            "checks": [check("SKILL-FRONTMATTER", False, str(error))],
        }

    line_count = len(skill_text.splitlines())
    checks.append(
        check(
            "SKILL-FRONTMATTER",
            keys == ["name", "description"],
            f"frontmatter keys={keys}",
        )
    )
    checks.append(
        check(
            "SKILL-LENGTH",
            300 <= line_count <= 500,
            f"SKILL.md lines={line_count}",
        )
    )
    checks.append(
        check(
            "SKILL-STAGES",
            all(re.search(rf"\bP{i}\b", body) for i in range(12)),
            "P0-P11 must all be routed",
        )
    )

    references_ok = True
    extended_references_ok = True
    long_toc_ok = True
    one_level_ok = True
    scope_ok = True
    for name in REFERENCE_NAMES:
        path = root / "references" / name
        if not path.is_file() or f"references/{name}" not in skill_text:
            references_ok = False
            continue
        text = path.read_text("utf-8")
        if len(text.splitlines()) > 100 and "## 目录" not in text[:4000]:
            long_toc_ok = False
        if re.search(r"\]\([^)]*references/[^)]*\.md", text):
            one_level_ok = False
        if "## 本文件负责" not in text or "## 本文件不负责" not in text:
            scope_ok = False
    checks.append(
        check(
            "DIRECT-REFERENCES",
            references_ok,
            "all nine references must exist and be linked directly",
        )
    )
    for name in EXTENDED_REFERENCE_NAMES:
        path = root / "references" / name
        if not path.is_file() or f"references/{name}" not in skill_text:
            extended_references_ok = False
            continue
        extended_text = path.read_text("utf-8", errors="replace")
        if "## 本文件负责" not in extended_text or "## 本文件不负责" not in extended_text:
            extended_references_ok = False
    checks.append(
        check(
            "EXTENDED-REFERENCES",
            extended_references_ok,
            "both integrated extension references must be directly routed and scoped",
        )
    )
    checks.append(
        check(
            "LONG-REFERENCE-TOC",
            long_toc_ok,
            "references over 100 lines require a TOC",
        )
    )
    checks.append(
        check(
            "ONE-LEVEL-DISCLOSURE",
            one_level_ok,
            "reference files may not create a deeper reference chain",
        )
    )
    checks.append(
        check(
            "REFERENCE-SCOPE",
            scope_ok,
            "each reference must declare responsibility and non-responsibility",
        )
    )

    policy_corpus = _collect_text(root, POLICY_ROOTS)
    archive_findings = _archive_runtime_findings(root)
    checks.append(
        check(
            "NO-ARCHIVE-RUNTIME-LINK",
            not archive_findings,
            "active runtime files may not link archived material"
            + (f"; findings={archive_findings}" if archive_findings else ""),
        )
    )
    checks.append(
        check(
            "NO-FIXED-QUOTAS",
            not any(phrase in policy_corpus for phrase in FIXED_QUOTAS),
            "fixed page/figure/algorithm/innovation quotas are forbidden",
        )
    )
    award_findings = _award_guarantee_findings(root)
    checks.append(
        check(
            "NO-AWARD-GUARANTEE",
            not award_findings,
            "quality target may not become an award guarantee"
            + (f"; findings={award_findings}" if award_findings else ""),
        )
    )
    placeholder_findings = _placeholder_findings(root)
    checks.append(
        check(
            "NO-PLACEHOLDERS",
            not placeholder_findings,
            "policy and production template files may not contain unfinished placeholders"
            + (
                f"; findings={placeholder_findings}"
                if placeholder_findings
                else ""
            ),
        )
    )

    def _collect_hygiene_findings() -> tuple[list[Path], list[Path]]:
        cache_dirs = [
            path
            for path in root.rglob("*")
            if path.is_dir()
            and path.name in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        ]
        bytecode_files = [
            path for path in root.rglob("*")
            if path.is_file()
            and (
                path.name in {".coverage", ".coverage.sqlite"}
                or path.suffix.lower() in {".pyc", ".pyo", ".tmp", ".bak", ".swp", ".swo"}
                # Agent-generated proxy reports belong in competition project
                # roots, never in the skill delivery itself.
                or (
                    path.parent == root
                    and path.name
                    in {
                        "ai_pattern_report.txt",
                        "plagiarism_proxy_report.txt",
                        "consistency_report.txt",
                    }
                )
            )
        ]
        return cache_dirs, bytecode_files

    protected_runtime_dirs = [
        path for path in root.rglob("*")
        if path.is_dir() and path.name in {".mmflow", ".git"}
    ]
    cache_paths, bytecode_paths = _collect_hygiene_findings()
    purged_count = 0
    if cache_paths or bytecode_paths:
        # Regenerable caches and bytecode are removed automatically so that a
        # stray __pycache__ from running the CLI cannot block delivery checks.
        # Protected runtime dirs (.mmflow, .git) are never auto-deleted.
        for stale_path in [*cache_paths, *bytecode_paths]:
            try:
                if stale_path.is_dir():
                    shutil.rmtree(stale_path)
                else:
                    stale_path.unlink()
                purged_count += 1
            except OSError:
                pass
        cache_paths, bytecode_paths = _collect_hygiene_findings()
    hygiene_leftovers = [*protected_runtime_dirs, *cache_paths, *bytecode_paths]
    checks.append(
        check(
            "DELIVERY-HYGIENE",
            not hygiene_leftovers,
            "skill delivery must not contain Python caches, bytecode, temporary files, .mmflow or .git directories"
            + (f"; auto-purged={purged_count}" if purged_count else "")
            + (f"; leftovers={[str(path.relative_to(root)) for path in hygiene_leftovers]}" if hygiene_leftovers else ""),
        )
    )

    # Figure coverage is intentionally checked as a capability of the skill,
    # rather than demanding an arbitrary number of figures in the skill
    # source.  Project-specific required roles are calculated from a problem
    # contract and enforced at P8 when a generated plan is present.
    figure_coverage_ok = (
        (root / "scripts/mmflow_core/figure_plan.py").is_file()
        and (root / "templates/visualization").is_dir()
        and "figures" in (root / "scripts/mmflow.py").read_text("utf-8")
    )
    checks.append(
        check(
            "FIGURE-COVERAGE",
            figure_coverage_ok,
            "figure coverage planner and Python visualization baseline must be routed",
        )
    )

    isolated_runtime_text = (
        (root / "scripts/mmflow_core/isolated_runtime.py").read_text("utf-8", errors="replace")
        if (root / "scripts/mmflow_core/isolated_runtime.py").is_file()
        else ""
    )
    test_runner_text = (
        (root / "scripts/run_tests.py").read_text("utf-8", errors="replace")
        if (root / "scripts/run_tests.py").is_file()
        else ""
    )
    isolation_runtime_ok = (
        bool(isolated_runtime_text)
        and "PYTHONPYCACHEPREFIX" in isolated_runtime_text
        and "prepare_isolated_run" in test_runner_text
        and (
            "not an OS security sandbox" in skill_text
            or "不是操作系统沙箱" in skill_text
            or "不是操作系统安全沙箱" in skill_text
        )
    )
    checks.append(
        check(
            "ISOLATION-RUNTIME",
            isolation_runtime_ok,
            "isolated runtime must route cache writes externally and disclose that directory isolation is not an OS security sandbox",
        )
    )

    try:
        manifest = json.loads(
            (root / "templates" / "template_manifest.json").read_text("utf-8")
        )
        manifest_ok = (
            manifest.get("schema") == "math-modeling-template-manifest/v1"
            and manifest.get("version") == 1
            and isinstance(manifest.get("templates"), list)
            and bool(manifest["templates"])
        )
        manifest_categories = {
            item.get("category")
            for item in manifest.get("templates", [])
            if isinstance(item, dict)
        }
        manifest_ok = manifest_ok and manifest_categories >= {
            "production",
            "analytics",
            "publication",
            "presentation",
            "quality",
            "visualization",
        }
        manifest_ok = manifest_ok and len({
            item.get("id") for item in manifest.get("templates", []) if isinstance(item, dict)
        }) == len(manifest.get("templates", []))
        manifest_ok = manifest_ok and all(
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("path"), str)
            and not Path(item["path"]).is_absolute()
            and ".." not in Path(item["path"]).parts
            and (root / item["path"]).is_file()
            for item in manifest.get("templates", [])
        )
    except Exception:
        manifest_ok = False
    checks.append(
        check(
            "TEMPLATE-MANIFEST",
            manifest_ok,
            "template manifest must be versioned, layered, path-safe, and complete",
        )
    )

    policy_ok = True
    for name in ("stages-v1.json", "evidence-v1.json", "schemas-v1.json"):
        try:
            value = json.loads(
                (root / "scripts/mmflow_core/policies" / name).read_text("utf-8")
            )
            policy_ok = (
                policy_ok
                and isinstance(value, dict)
                and value.get("version") == 1
            )
        except Exception:
            policy_ok = False
    checks.append(
        check(
            "POLICY-JSON",
            policy_ok,
            "all policy files must parse and have version 1",
        )
    )

    try:
        demo = json.loads(
            (root / "templates/examples/artifact-class.json").read_text("utf-8")
        )
        production = json.loads(
            (root / "templates/production/artifact-class.json").read_text("utf-8")
        )
        result_contract = json.loads(
            (root / "templates/production/result-contract.json").read_text("utf-8")
        )
        template_ok = (
            demo.get("artifact_class") == "demo"
            and demo.get("production_eligible") is False
            and production.get("requires_controlled_execution") is True
            and production.get("requires_explicit_implementation") is True
            and result_contract.get("schema") == "mmflow-result-contract/v1"
            and result_contract.get("results") == {}
        )
    except Exception:
        template_ok = False
    checks.append(
        check(
            "TEMPLATE-ISOLATION",
            template_ok,
            "demo and production template metadata must be explicit",
        )
    )

    try:
        metadata_keys, metadata = parse_openai_yaml(root / "agents/openai.yaml")
        metadata_ok = (
            metadata_keys
            == {"display_name", "short_description", "default_prompt"}
            and 25 <= len(metadata["short_description"]) <= 64
            and "$math-modeling" in metadata["default_prompt"]
        )
    except Exception:
        metadata_ok = False
    checks.append(
        check(
            "AGENT-METADATA",
            metadata_ok,
            "agents/openai.yaml must match the skill creator contract",
        )
    )

    # Contract conformance: policy and CLI must agree with the implementation.
    cli_text = (root / "scripts/mmflow.py").read_text("utf-8")
    cli_commands: set[str] = set()
    for match in re.finditer(r"add_parser\(\s*\"([^\"]+)\"", cli_text):
        cli_commands.add(match.group(1))
    for match in re.finditer(r"for name in \((\"[^\"]+\"(?:, )*)+\s*\)\s*:", cli_text):
        for name in re.findall(r"\"([^\"]+)\"", match.group(0)):
            cli_commands.add(name)
    required_cli = {
        "release-status",
        "invalidate",
        "scan-privacy",
        "close-finding",
        "resume",
        "doctor",
        "rollback",
        "checkpoint",
        "package",
        "reproduce",
        "register-input",
    }
    forbidden_cli = {"revise-entity"}
    register_kinds_ok = all(
        f'"{name}": "{kind}"' in cli_text
        for name, kind in (
            ("register-artifact", "artifact"),
            ("register-result", "result"),
            ("register-claim", "claim"),
            ("register-formula", "formula"),
            ("register-citation", "citation"),
            ("register-figure", "figure"),
            ("register-finding", "finding"),
            ("register-evidence", "evidence"),
        )
    )
    missing = sorted(required_cli - cli_commands)
    checks.append(
        check(
            "CLI-CONTRACT",
            not missing and not (forbidden_cli & cli_commands) and register_kinds_ok,
            "CLI must expose the v2 command surface and drop raw revise-entity"
            + (f"; missing={missing}" if missing else "")
            + ("; register-kind mapping incomplete" if not register_kinds_ok else ""),
        )
    )

    try:
        schemas = json.loads(
            (root / "scripts/mmflow_core/policies/schemas-v1.json").read_text("utf-8")
        )
        evidence = json.loads(
            (root / "scripts/mmflow_core/policies/evidence-v1.json").read_text("utf-8")
        )
        stages = json.loads(
            (root / "scripts/mmflow_core/policies/stages-v1.json").read_text("utf-8")
        )
        contracts = schemas.get("evidence_contracts", {})
        stage_requirements = evidence.get("stage_requirements", {})
        missing_contracts = [
            evidence_type
            for definition in stage_requirements.values()
            for evidence_type in definition.get("evidence_types", [])
            if evidence_type not in contracts
        ]
        matrix = evidence.get("evidence_stage_matrix", {})
        unmapped_types = [
            evidence_type
            for evidence_type in contracts
            if evidence_type not in matrix
        ]
        reference_files = {
            name
            for stage in stages.get("stages", [])
            for name in stage.get("references", [])
        }
        missing_references = [
            name
            for name in reference_files
            if not (root / name).is_file()
        ]
        checks.append(
            check(
                "POLICY-EVIDENCE-CONTRACT",
                not missing_contracts and not unmapped_types,
                "every required evidence type must have a schema contract and a stage matrix entry"
                + (f"; missing={missing_contracts}" if missing_contracts else "")
                + (f"; unmapped={unmapped_types}" if unmapped_types else ""),
            )
        )
        checks.append(
            check(
                "STAGE-REFERENCE-CONTRACT",
                not missing_references,
                "stage policy references must name existing reference files"
                + (f"; missing={missing_references}" if missing_references else ""),
            )
        )
        dependency_fields = schemas.get("evidence_dependency_fields", {})
        missing_dependencies = [
            evidence_type
            for evidence_type in contracts
            if evidence_type not in dependency_fields
        ]
        checks.append(
            check(
                "EVIDENCE-DEPENDENCY-CONTRACT",
                not missing_dependencies,
                "every evidence type must declare dependency fields"
                + (f"; missing={missing_dependencies}" if missing_dependencies else ""),
            )
        )
    except Exception as error:
        checks.append(
            check(
                "POLICY-CONFORMANCE",
                False,
                f"policy conformance check failed: {type(error).__name__}: {error}",
            )
        )

    return {
        "status": (
            "PASS"
            if all(item["status"] == "PASS" for item in checks)
            else "FAIL"
        ),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = validate_skill_root(args.skill_root)
    if args.json:
        print(
            json.dumps(
                report,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    else:
        for item in report["checks"]:
            print(f"{item['status']} {item['rule_id']}: {item['reason']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
