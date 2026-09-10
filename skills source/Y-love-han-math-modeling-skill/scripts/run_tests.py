"""Run skill tests from an external snapshot with auditable progress.

The source skill directory is never used as a test working directory.  The
wrapper emits JSONL progress on stderr and a single machine-readable summary
on stdout, so callers can both stream progress and consume the final result.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from time import monotonic


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SKILL_ROOT))

from scripts.mmflow_core.isolated_runtime import prepare_isolated_run


QUICK_FILES = [
    "tests/test_template_manifest.py",
    "tests/test_template_adapter.py",
    "tests/test_quality_profiles.py",
    "tests/test_problem_reference_implementation.py",
    "tests/test_clean_delivery.py",
    "tests/test_isolated_runtime.py",
    "tests/test_run_tests_isolation.py",
]
_FULL_GROUP_HINTS = [
    ("core", ["tests/test_audit_domains.py", "tests/test_bindings_contract.py", "tests/test_blocked_lifecycle.py", "tests/test_error_classification.py", "tests/test_evidence_dependencies.py", "tests/test_formula_citation_contract.py", "tests/test_invalidate.py", "tests/test_locking_journal.py", "tests/test_next_doctor.py", "tests/test_requirements_compliance.py", "tests/test_result_claim_policy.py", "tests/test_scan_context.py", "tests/test_split_entity.py", "tests/test_stage_epoch.py"]),
    ("workflow", ["tests/test_full_workflow.py", "tests/test_acceptance_round2.py", "tests/test_forward_behavior_contract.py", "tests/test_integrated_contract.py", "tests/test_publication_closure.py", "tests/test_review_quality.py", "tests/test_quality_profiles.py"]),
    ("runner", ["tests/test_runner_hardening.py", "tests/test_figure_sidecar.py", "tests/test_finding_closure.py"]),
    ("delivery", ["tests/test_template_manifest.py", "tests/test_template_adapter.py", "tests/test_problem_reference_implementation.py", "tests/test_release_tools.py", "tests/test_clean_delivery.py", "tests/test_delivery_privacy.py"]),
]
FULL_GROUP_NAMES = tuple(name for name, _files in _FULL_GROUP_HINTS) + ("figures-docs",)


def _all_test_files() -> list[str]:
    return sorted(
        path.relative_to(SKILL_ROOT).as_posix()
        for path in (SKILL_ROOT / "tests").glob("test_*.py")
        if path.is_file()
    )


def _full_groups() -> list[tuple[str, list[str]]]:
    """Return deterministic groups covering every discovered test module."""
    all_files = _all_test_files()
    assigned: dict[str, str] = {}
    groups: list[tuple[str, list[str]]] = []
    for name, hinted in _FULL_GROUP_HINTS:
        selected = [path for path in hinted if path in all_files and path not in assigned]
        for path in selected:
            assigned[path] = name
        if selected:
            groups.append((name, selected))
    remaining = [path for path in all_files if path not in assigned]
    if remaining:
        groups.append(("figures-docs", remaining))
    covered = [path for _name, files in groups for path in files]
    if sorted(covered) != all_files or len(covered) != len(set(covered)):
        raise RuntimeError("full test grouping does not cover each test file exactly once")
    return groups


def _progress(event: str, **payload: object) -> dict[str, object]:
    item = {"schema": "mmflow-test-progress/v1", "event": event, **payload}
    print(json.dumps(item, ensure_ascii=False), file=sys.stderr, flush=True)
    return item


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated math-modeling skill tests")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--unit", metavar="NODE", help="one pytest node or test file")
    scope.add_argument("--quick", action="store_true", help="run the fast contract suite")
    scope.add_argument("--full", action="store_true", help="run stable full-suite groups")
    parser.add_argument(
        "--scope",
        choices=("unit", "quick", "full"),
        help="explicit spelling for test scope; --unit/--quick/--full remain compatible",
    )
    parser.add_argument("--skill-root", default=str(SKILL_ROOT))
    parser.add_argument("--output-root", help="external directory for snapshots and reports")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help=(
            "per-group timeout in seconds; when omitted, each group gets an "
            "adaptive budget of max(300, 240s x target count) so slow machines "
            "are not spuriously failed while hangs stay bounded"
        ),
    )
    parser.add_argument(
        "--group",
        choices=FULL_GROUP_NAMES,
        help="run one named full-suite group (implies --full)",
    )
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.group and (args.unit or args.quick or args.scope == "unit" or args.scope == "quick"):
        parser.error("--group can only be used with the full test scope")
    selected = (
        "unit" if args.unit else "quick" if args.quick else "full"
        if args.full or args.group
        else args.scope or "full"
    )
    if args.scope and args.scope != selected:
        parser.error("--scope conflicts with explicit scope flag")
    if selected == "unit" and not args.unit:
        parser.error("--scope unit requires --unit NODE")
    args.selected_scope = selected
    if args.pytest_args[:1] == ["--"]:
        args.pytest_args = args.pytest_args[1:]
    return args


def _groups(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    if args.selected_scope == "unit":
        return [("unit", [args.unit])]
    if args.selected_scope == "quick":
        nested = os.environ.get("MMFLOW_TEST_WRAPPER_CHILD") == "1"
        selected = list(QUICK_FILES)
        if nested:
            selected = [path for path in selected if path != "tests/test_run_tests_isolation.py"]
        return [("quick", selected)]
    groups = _full_groups()
    if args.group:
        groups = [item for item in groups if item[0] == args.group]
        if not groups:
            raise RuntimeError(f"full test group is unavailable: {args.group}")
    return groups


def _pytest_command(targets: list[str], extra: list[str]) -> list[str]:
    return [sys.executable, "-m", "pytest", "-q", *targets, *extra]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    skill_root = Path(args.skill_root).resolve()
    output_root = Path(args.output_root).resolve() if args.output_root else None
    started = monotonic()
    context = prepare_isolated_run(skill_root, f"tests-{args.selected_scope}", output_root=output_root)
    events: list[dict[str, object]] = []
    groups: list[dict[str, object]] = []
    overall_returncode = 0
    try:
        for name, targets in _groups(args):
            begin = _progress("group_started", group=name, targets=targets)
            events.append(begin)
            child_environment = None
            # The quick contract includes this release-tool test, which calls
            # the wrapper recursively.  Mark the child so it omits the
            # recursive wrapper-isolation test while still exercising all
            # other quick checks; otherwise the test suite recurses forever
            # and reports a false failure.
            if args.selected_scope == "quick":
                child_environment = {"MMFLOW_TEST_WRAPPER_CHILD": "1"}
            if args.timeout is not None:
                budget = args.timeout
            else:
                # Adaptive default: slow machines legitimately need minutes
                # per group; scaling by target count keeps hang detection
                # bounded without spuriously failing long groups.
                budget = max(300.0, 240.0 * len(targets))
            result = context.command(
                _pytest_command(targets, args.pytest_args),
                timeout=budget,
                environment=child_environment,
            )
            group = {
                "name": name,
                "targets": targets,
                "command": result.command,
                "returncode": result.returncode,
                "duration_seconds": result.duration_seconds,
                "timed_out": result.timed_out,
                "timeout_seconds": budget,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            groups.append(group)
            end = _progress(
                "group_finished",
                group=name,
                returncode=result.returncode,
                duration_seconds=result.duration_seconds,
                timed_out=result.timed_out,
            )
            events.append(end)
            if result.returncode:
                overall_returncode = result.returncode or 1
                break
    except Exception as error:
        overall_returncode = 2
        events.append(_progress("runner_error", error=f"{type(error).__name__}: {error}"))
    # The isolated runner deliberately records failures, but pre-existing
    # cache/bytecode entries in a source tree are hygiene findings rather than
    # a reason to relabel an otherwise successful test process.  Delivery and
    # validator gates still fail closed on those findings.
    report = context.finalize(success=overall_returncode == 0, preserve_on_failure=True)
    payload = {
        "schema": "math-modeling-test-report/v2",
        "status": "PASS" if overall_returncode == 0 and report.source_unchanged else "FAIL",
        "scope": args.selected_scope,
        "skill_root": str(skill_root),
        "returncode": overall_returncode,
        "duration_seconds": round(monotonic() - started, 3),
        "groups": groups,
        "progress_events": events,
        "source_diff": report.source_diff,
        "pollution": report.pollution,
        "source_unchanged": report.source_unchanged,
        "isolation_report": str(report.report_path),
        "preserved_run_dir": str(report.run_root) if report.preserved_run_dir else None,
        "reproduction": {
            "scope": args.selected_scope,
            "command": _reproduction_command(args, skill_root),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else (overall_returncode or 1)


def _reproduction_command(args: argparse.Namespace, skill_root: Path) -> list[str]:
    """Build a complete, directly runnable replay command for this scope."""
    command = [sys.executable, str(Path(__file__).resolve()), "--skill-root", str(skill_root)]
    if args.output_root:
        command.extend(["--output-root", str(Path(args.output_root).resolve())])
    if args.selected_scope == "unit":
        command.extend(["--unit", str(args.unit)])
    else:
        command.append(f"--{args.selected_scope}")
        if args.group:
            command.extend(["--group", args.group])
    if args.timeout is not None:
        # Explicit budgets must be replayed verbatim; the adaptive default is
        # deterministic per group size, so omitted flags reproduce faithfully.
        command.extend(["--timeout", str(args.timeout)])
    if args.pytest_args:
        command.append("--")
        command.extend(args.pytest_args)
    return command


if __name__ == "__main__":
    raise SystemExit(main())
