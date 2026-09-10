from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.mmflow_core.audit import (
    create_delivery_archive,
    reconcile_changed_artifacts,
    run_domain_audit,
    semantic_stage_check,
)
from scripts.mmflow_core.bindings import (
    parse_bindings,
    render_latex_bindings,
    render_project_latex_bindings,
    scan_project_latex_sources,
    scan_unbound_numbers,
)
from scripts.mmflow_core.canonical import (
    atomic_write_json,
    canonical_json_bytes,
    is_reparse_point,
    resolve_regular_file_within,
    resolve_within,
    sha256_bytes,
    sha256_file,
)
from scripts.mmflow_core.errors import (
    ConfigError,
    ExitCode,
    GateFailedError,
    IntegrityError,
    MMFlowError,
)
from scripts.mmflow_core.gates import GateEngine, evidence_fingerprint
from scripts.mmflow_core.lineage import (
    LineageGraph,
    invalidate_stage_downstream,
    rerun_scope_from,
    stage_index,
)
from scripts.mmflow_core.locking import ProjectLock
from scripts.mmflow_core.privacy import scan_manifest_files
from scripts.mmflow_core.project import (
    create_checkpoint,
    doctor,
    initialize_project,
    load_policy,
    load_runtime,
    next_stage,
    read_json_object,
)
from scripts.mmflow_core.release import compute_release_label
from scripts.mmflow_core.runner import ExecutionRequest, ExecutionRunner


REGISTER_KINDS = {
    "register-artifact": "artifact",
    "register-result": "result",
    "register-claim": "claim",
    "register-formula": "formula",
    "register-citation": "citation",
    "register-figure": "figure",
    "register-finding": "finding",
    "register-evidence": "evidence",
    "register-split": "split",
}


FIXED_STAGE_COMMANDS = {
    "render-bindings": "P8",
    "scan-manuscript": "P8",
    "reproduce": "P9",
    "review": "P10",
}


def _tree_sha256(root: Path, *, exclude_relative: set[str] | None = None) -> str:
    excluded = {item.replace("\\", "/") for item in (exclude_relative or set())}
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        if relative == ".mmflow/project.lock":
            # Advisory writer-lock metadata is runtime coordination state, not
            # project evidence.  On Windows it is intentionally unreadable
            # while locked, so it must never participate in a content digest.
            continue
        if any(part in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"} for part in Path(relative).parts):
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _lexical_absolute(path: Path | str) -> Path:
    """Make an absolute path without following links or reparse points."""
    return Path(os.path.abspath(os.fspath(Path(path))))


def _assert_path_chain_safe(path: Path | str) -> None:
    """Reject links/reparse points in an existing path component chain."""
    current = _lexical_absolute(path)
    while True:
        if is_reparse_point(current):
            raise IntegrityError(f"migration path contains a link or reparse point: {current}")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _assert_tree_safe(root: Path) -> None:
    """Fail closed if a migration source/candidate contains any link."""
    root = _lexical_absolute(root)
    _assert_path_chain_safe(root)
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            raise IntegrityError(f"migration tree cannot be inspected: {current}") from error
        for entry in entries:
            candidate = Path(entry.path)
            if is_reparse_point(candidate):
                raise IntegrityError(
                    f"migration tree contains a link or reparse point: {candidate}"
                )
            try:
                if entry.is_dir(follow_symlinks=False):
                    pending.append(candidate)
            except OSError as error:
                raise IntegrityError(f"migration tree cannot inspect entry: {candidate}") from error


def _lexists(path: Path | str) -> bool:
    """Existence check that also sees dangling symlinks."""
    return os.path.lexists(os.fspath(path))


def _migration_plan(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the immutable v1 facts used by a migration plan.

    Callers holding the source writer lock receive one consistent snapshot;
    dry-run callers intentionally remain read-only and may only report the
    state observed during their scan.
    """
    _assert_tree_safe(root)
    contract = read_json_object(root / ".mmflow/contract.json")
    v1_ledger_head = None
    head_path = root / ".mmflow/ledger-head.json"
    if head_path.is_file():
        v1_ledger_head = read_json_object(head_path).get("head_sha256")
    policy_lock = read_json_object(root / ".mmflow/policy-lock.json")
    evidence_needing_revalidation = sorted(
        {
            str(record["payload"].get("evidence_type"))
            for record in _scan_v1_registry(root)
        }
    )
    return contract, {
        "status": "migration_plan",
        "v1_run_id": contract.get("run_id"),
        "v1_ledger_head": v1_ledger_head,
        "v1_policy_sha256": policy_lock.get("policy_sha256"),
        "recommendation": (
            "create a new v2 project run directory and import only "
            "immutable artifacts by hash; v1 evidence gains no v2 stage "
            "epoch automatically"
        ),
        "evidence_needing_revalidation": evidence_needing_revalidation,
        "v1_complete_mapping": "refused",
        "input_sha256": _tree_sha256(root),
        "mapping": {
            "contract_version": {"from": 1, "to": 2},
            "skill_version": {"from": contract.get("skill_version"), "to": "2.0.0"},
        },
    }


@contextmanager
def _migration_locks(root: Path, output: Path, run_id: str | None = None):
    """Serialize a migration with writers of both its source and destination.

    The output lock lives in a dedicated sibling lock project, so it can be
    acquired before the output project exists.  Its directory is retained as
    a harmless coordination marker; the advisory OS lock, rather than the
    file's presence, establishes ownership.
    """
    output_lock_root = output.parent / f".{output.name}.mmflow-migration-lock"
    if _lexical_absolute(output_lock_root) == _lexical_absolute(root):
        raise GateFailedError("migration source and destination lock paths must differ")
    _assert_path_chain_safe(output_lock_root)
    source_lock = ProjectLock(root, run_id)
    output_lock = ProjectLock(output_lock_root, None)
    source_lock.acquire()
    try:
        output_lock.acquire()
        try:
            yield
        finally:
            output_lock.release()
    finally:
        source_lock.release()

# Every state-mutating command must hold the project single-writer lock.
# 注：audit 本身各分域只读，但被列入 MUTATING —— 它在 _reconcile_for_command
# 中会触发 reconcile_changed_artifacts，内容漂移的 VALID artifact 可级联
# STALE 失效并回退阶段；且持锁保证 audit 报告序号与并发 gate 互斥。
# promote-artifact / retire-artifact 同理必须持单写者锁。
MUTATING_COMMANDS = {
    "init",
    "begin",
    "gate",
    "advance",
    "rollback",
    "register-input",
    *REGISTER_KINDS,
    "run",
    "render-bindings",
    "reproduce",
    "review",
    "close-finding",
    "invalidate",
    "batch-register",
    "retire-artifact",
    "promote-artifact",
    "package",
    "checkpoint",
    "audit",
    "scan-privacy",
    "resume",
}


def _emit(value: Any, json_mode: bool) -> None:
    if json_mode:
        sys.stdout.write(
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
    elif isinstance(value, dict):
        for key, item in value.items():
            sys.stdout.write(f"{key}: {item}\n")
    else:
        sys.stdout.write(str(value) + "\n")


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--json", action="store_true")


def _policy_object(runtime_or_root, name: str) -> dict[str, Any]:
    skill_root = getattr(runtime_or_root, "skill_root", None)
    base = (
        Path(skill_root) if skill_root is not None else Path(runtime_or_root)
    ) / "scripts/mmflow_core/policies"
    return read_json_object(base / name)


def _schema_payload(skill_root: Path, evidence_type: str | None) -> dict[str, Any]:
    """Read-only introspection: machine contract for one or all evidence types.

    Merges the required content keys, dependency-extraction paths and the
    audited row-field notes so callers never have to reverse-engineer the
    semantic checkers in audit.py to build a registrable payload.
    """
    schemas = read_json_object(
        skill_root / "scripts/mmflow_core/policies/schemas-v1.json"
    )
    contracts = schemas.get("evidence_contracts", {})
    dependencies = schemas.get("evidence_dependency_fields", {})
    notes = schemas.get("evidence_content_field_notes", {})
    dimensions = schemas.get("quality_dimensions", {})
    selected = (
        [evidence_type]
        if evidence_type is not None
        else sorted(contracts)
    )
    unknown = [item for item in selected if item not in contracts]
    if unknown:
        raise ConfigError(f"unknown evidence_type: {', '.join(unknown)}")
    items = {
        item: {
            "required_content_keys": list(contracts[item]),
            "dependency_fields": list(dependencies.get(item, [])),
            "audited_field_notes": notes.get(item, {}),
            "stage_matrix_hint": None,
        }
        for item in selected
    }
    payload: dict[str, Any] = {
        "schema": "mmflow-evidence-schema/v1",
        "policy": "schemas-v1",
        "evidence_types": items,
        "quality_dimensions": dimensions,
    }
    try:
        matrix = read_json_object(
            skill_root / "scripts/mmflow_core/policies/evidence-v1.json"
        ).get("evidence_stage_matrix", {})
        for item, value in items.items():
            value["stage_matrix_hint"] = sorted(matrix.get(item, []))
    except MMFlowError:
        pass
    return payload


def _adapters_payload() -> dict[str, Any]:
    """Read-only introspection: legal validation adapter names and waivers."""
    from scripts.mmflow_core.applicability import (
        CLAIM_ADAPTERS,
        MODEL_ADAPTERS,
        TRAIT_ADAPTERS,
        WAIVER_RULES,
    )

    return {
        "schema": "mmflow-adapter-registry/v1",
        "traits": {key: sorted(value) for key, value in sorted(TRAIT_ADAPTERS.items())},
        "claim_types": {key: sorted(value) for key, value in sorted(CLAIM_ADAPTERS.items())},
        "model_families": {key: sorted(value) for key, value in sorted(MODEL_ADAPTERS.items())},
        "waiver_rules": {
            rule_id: {"adapter": adapter}
            for rule_id, (adapter, _predicate) in sorted(WAIVER_RULES.items())
        },
        "all_adapter_names": sorted(
            {
                name
                for group in (TRAIT_ADAPTERS, CLAIM_ADAPTERS, MODEL_ADAPTERS)
                for names in group.values()
                for name in names
            }
        ),
    }


def _cookbook_payload(skill_root: Path, stage: str | None) -> dict[str, Any]:
    """Read-only introspection: registration cookbook path(s) for a stage."""
    from scripts.mmflow_core.lineage import STAGE_INDEX

    stages_policy = read_json_object(
        skill_root / "scripts/mmflow_core/policies/stages-v1.json"
    )
    by_id = {
        entry.get("id"): entry
        for entry in stages_policy.get("stages", [])
        if isinstance(entry, dict)
    }
    cookbook_name = "references/evidence-registration-cookbook.md"
    sections: dict[str, Any] = {}
    if stage is not None:
        if stage not in STAGE_INDEX:
            raise ConfigError(f"unknown stage: {stage}")
        definition = by_id.get(stage, {})
        sections = {
            "stage": stage,
            "name": definition.get("name"),
            "evidence_requirements": read_json_object(
                skill_root / "scripts/mmflow_core/policies/evidence-v1.json"
            )
            .get("stage_requirements", {})
            .get(stage, {}),
            "references": [
                reference
                for reference in definition.get("references", [])
                if reference != cookbook_name
            ],
            "cookbook": cookbook_name,
        }
    else:
        sections = {
            "stages": sorted(by_id),
            "cookbook": cookbook_name,
        }
    return {"schema": "mmflow-registration-cookbook/v1", **sections}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mmflow")
    sub = parser.add_subparsers(dest="command", required=True)

    schema_parser = sub.add_parser("schema")
    schema_parser.add_argument("--skill-root", default=None)
    schema_parser.add_argument(
        "--evidence-type", default=None, help="省略时输出全部证据类型契约"
    )
    schema_parser.add_argument("--json", action="store_true")

    adapters_parser = sub.add_parser("adapters")
    adapters_parser.add_argument("--skill-root", default=None)
    adapters_parser.add_argument("--json", action="store_true")

    cookbook_parser = sub.add_parser("cookbook")
    cookbook_parser.add_argument("--skill-root", default=None)
    cookbook_parser.add_argument("--stage", default=None)
    cookbook_parser.add_argument("--json", action="store_true")

    doctor_parser = sub.add_parser("doctor")
    _add_common(doctor_parser)
    doctor_parser.add_argument("--probe-write", action="store_true")
    doctor_parser.add_argument(
        "--probe-network",
        action="store_true",
        help="显式启用一次短超时网络连通性探测（默认零外部流量）",
    )
    init_parser = sub.add_parser("init")
    _add_common(init_parser)
    init_parser.add_argument("--competition", required=True)
    init_parser.add_argument("--edition", required=True)
    init_parser.add_argument(
        "--quality-profile",
        default="adaptive",
        help=(
            "quality contract profile; adaptive is backward-compatible, "
            "special-prize enables scientific-depth evidence gates"
        ),
    )

    for name in ("status", "next", "advance", "audit", "checkpoint", "release-status"):
        _add_common(sub.add_parser(name))

    export_claims = sub.add_parser("export-claims")
    _add_common(export_claims)
    export_claims.add_argument(
        "--question", default=None, help="仅导出该 question_id 的 claim"
    )
    export_claims.add_argument(
        "--output",
        default=None,
        help="写入 JSON 文件（已存在则拒绝）；省略时经 --json 输出到 stdout",
    )

    resume_parser = sub.add_parser("resume")
    _add_common(resume_parser)
    resume_parser.add_argument("--resolve-blocked", action="store_true")
    resume_parser.add_argument("--evidence", action="append")
    resume_parser.add_argument(
        "--from-checkpoint",
        default=None,
        help=(
            "可选：读取 .mmflow/checkpoints/ 下的断点文件，校验其与当前 "
            "run/head 一致后，把 work_queue 作为恢复辅助合并进返回值；"
            "事实源仍是账本重放"
        ),
    )

    begin_parser = sub.add_parser("begin")
    _add_common(begin_parser)
    begin_parser.add_argument("stage")

    gate_parser = sub.add_parser("gate")
    _add_common(gate_parser)
    gate_parser.add_argument("stage")

    rollback_parser = sub.add_parser("rollback")
    _add_common(rollback_parser)
    rollback_parser.add_argument("stage")
    rollback_parser.add_argument("--reason", required=True)

    promote_parser = sub.add_parser("promote-artifact")
    _add_common(promote_parser)
    promote_parser.add_argument(
        "--id", required=True,
        help="production artifact ID to rebind to a valid same-run execution (class is immutable)",
    )
    promote_parser.add_argument("--execution-id", required=True, help="execution ID that produced/validated this artifact")

    retire_parser = sub.add_parser("retire-artifact")
    _add_common(retire_parser)
    retire_parser.add_argument("--id", required=True, help="artifact/entity ID to retire")
    retire_parser.add_argument("--reason", required=True, help="why this generation is being retired")

    batch_parser = sub.add_parser("batch-register")
    _add_common(batch_parser)
    batch_parser.add_argument("--file", required=True, help="JSON file with array of {kind, payload} entries")

    run_parser = sub.add_parser("run")
    _add_common(run_parser)
    run_parser.add_argument("--stage", required=True)
    run_parser.add_argument("--question", required=True)
    run_parser.add_argument("--role", required=True)
    run_parser.add_argument("--class", dest="artifact_class", required=True)
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("program", nargs=argparse.REMAINDER)

    input_parser = sub.add_parser("register-input")
    _add_common(input_parser)
    input_parser.add_argument("--id", required=True)
    input_parser.add_argument("--type", required=True)
    input_parser.add_argument("--path", required=True)

    for name in REGISTER_KINDS:
        register = sub.add_parser(name)
        _add_common(register)
        register.add_argument("--file", required=True)

    render = sub.add_parser("render-bindings")
    _add_common(render)
    render.add_argument("--source", required=True)
    render.add_argument("--output", required=True)

    scan = sub.add_parser("scan-manuscript")
    _add_common(scan)
    scan.add_argument("--source", required=True)

    reproduce = sub.add_parser("reproduce")
    _add_common(reproduce)
    reproduce.add_argument("--execution", required=True)

    review = sub.add_parser("review")
    _add_common(review)
    review.add_argument("--file", required=True)

    invalidate = sub.add_parser("invalidate")
    _add_common(invalidate)
    invalidate.add_argument("--id", required=True)
    invalidate.add_argument("--reason", required=True)

    close = sub.add_parser("close-finding")
    _add_common(close)
    close.add_argument("--id", required=True)
    close.add_argument("--closure", required=True)
    close.add_argument("--reason", required=True)
    close.add_argument("--mode", choices=("CLOSED", "ACCEPTED_LIMITATION"), default="CLOSED")

    scan_privacy = sub.add_parser("scan-privacy")
    _add_common(scan_privacy)
    scan_privacy.add_argument("--manifest", required=True)
    scan_privacy.add_argument("--output", required=True)
    scan_privacy.add_argument(
        "--force-new-name",
        action="store_true",
        help="输出已存在时自动追加序号（scan-1.json…）而不是报错",
    )

    package_parser = sub.add_parser("package")
    _add_common(package_parser)
    package_parser.add_argument("--manifest", required=True)
    package_parser.add_argument("--output", required=True)
    package_parser.add_argument("--candidate", action="store_true")
    package_parser.add_argument(
        "--force-new-name",
        action="store_true",
        help="包文件已存在时自动追加序号而不是报错",
    )

    migrate = sub.add_parser("migrate")
    _add_common(migrate)
    migrate.add_argument("--dry-run", "--plan", dest="plan", action="store_true")
    migrate.add_argument("--apply", action="store_true")
    migrate.add_argument("--output")

    figures = sub.add_parser("figures")
    figures_sub = figures.add_subparsers(dest="figures_command", required=True)
    plan_parser = figures_sub.add_parser("plan")
    _add_common(plan_parser)
    plan_parser.add_argument("--contract", required=True)
    verify_parser = figures_sub.add_parser("verify")
    _add_common(verify_parser)
    verify_parser.add_argument("--plan", required=True)
    verify_parser.add_argument("--figures", required=True)
    return parser


def _register_payload(runtime, kind: str, source: str) -> dict[str, Any]:
    source_path = resolve_regular_file_within(runtime.project_root, source)
    payload = read_json_object(source_path)
    payload.setdefault("run_id", runtime.run_id)
    state = runtime.workflow.state()
    stage = state.get("active_stage")
    if stage is None and isinstance(state.get("blocked"), dict):
        # A blocked workflow still allows stage evidence to be produced:
        # resolution evidence must be registered while the stage is blocked.
        stage = state["blocked"].get("stage")
    return runtime.registry.register(kind, payload, stage=stage)


# Commands that must never mutate workflow facts.  Reconciling artifact
# drift (which may cascade INVALID/STALE and roll stages back) is a state
# transition, so read-only commands are exempted here; drift is still
# detected by every mutating command, by `gate`, and by `audit`.
READ_ONLY_COMMANDS = frozenset({
    "status",
    "next",
    "doctor",
    "export-claims",
    "release-status",
})


def _reconcile_for_command(runtime, command: str) -> None:
    if command in READ_ONLY_COMMANDS:
        return
    if command not in {"register-input", *REGISTER_KINDS, "run", "audit"}:
        reconcile_changed_artifacts(runtime)


def _require_active_stage(runtime, expected: str) -> None:
    state = runtime.workflow.state()
    if state["active_stage"] != expected:
        raise GateFailedError(
            f"command requires {expected} to be the active stage"
        )


def _block_payload_from_report(report: dict[str, Any]) -> dict[str, Any] | None:
    for check in report.get("checks", []):
        block = check.get("block")
        if isinstance(block, dict) and block:
            payload = dict(block)
            payload.setdefault("reason", str(check.get("reason", "")))
            return payload
    return None


@contextmanager
def _writer_lock(project_root: str, run_id: str | None = None):
    lock = ProjectLock(project_root, run_id)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()



def _autoregister_run_evidences(runtime, stage, exec_payload, result):
    """U2: after a VALID production run, register the production_execution
    evidence and - when an output uses schema mmflow-result-contract/v1 -
    its result entities plus one structured_results evidence.

    Duplicate-type guard: if a VALID record of the type already exists
    (e.g. registered manually by a driver), registration is skipped so the
    exactly-one-per-type gate invariant can never be violated.  Any
    structural surprise aborts silently; nothing is fabricated.
"""
    registered = []
    auto_errors: list[str] = []
    try:
        def _type_valid(etype):
            return any(
                rec["payload"].get("status") == "VALID"
                and rec["payload"].get("evidence_type") == etype
                for rec in runtime.registry.iter_latest("evidence"))

        exec_id = exec_payload["execution_id"]
        if not _type_valid("production_execution"):
            runtime.registry.register("evidence", {
                "evidence_id": f"ev_exec_{exec_id[:12]}",
                "evidence_type": "production_execution",
                "run_id": runtime.run_id,
                "status": "VALID",
                "content": {"execution_ids": [exec_id]},
                "supports": [exec_id],
            }, stage=stage)
            registered.append(f"ev_exec_{exec_id[:12]}")

        if _type_valid("structured_results"):
            return registered, auto_errors

        solve_art = next(
            (a for a in result.artifacts
             if a["payload"]["logical_output_path"].endswith(".json")),
            None)
        if solve_art is None:
            return registered, auto_errors
        from decimal import Decimal, ROUND_HALF_EVEN

        document = json.loads(
            (runtime.project_root
             / solve_art["payload"]["relative_path"]).read_text("utf-8"))
        if document.get("schema") != "mmflow-result-contract/v1":
            return registered, auto_errors

        result_ids = []
        for key, node in document.items():
            if key == "schema" or not isinstance(node, dict):
                continue
            value = node.get("value")
            if value is None:
                continue
            rendered = str(Decimal(str(value)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN))
            rid = f"res_{exec_id[:8]}_{str(key).lower()}"
            runtime.registry.register("result", {
                "result_id": rid,
                "run_id": runtime.run_id,
                "status": "VALID",
                "artifact_id": solve_art["entity_id"],
                "execution_id": exec_id,
                "question_id": str(key),
                "model_id": str(node.get("model_id", "declared_model")),
                "result_kind": "scalar",
                "metric": str(node["metric"]),
                "unit": str(node["unit"]),
                "direction": node["direction"],
                "scenario": str(node["scenario"]),
                "dataset_split_id": str(node["dataset_split_id"]),
                "sample_size": node.get("sample_size", 1),
                "measurements": [{"t": str(node["metric"]), "v": value}],
                "source_locator": {"format": "json_pointer",
                                   "pointer": f"/{key}"},
                "display": {"decimals": 4, "rendered": rendered,
                            "rounding": "half_even"},
                "value": value,
            }, stage=stage)
            result_ids.append(rid)

        if result_ids and not _type_valid("structured_results"):
            runtime.registry.register("evidence", {
                "evidence_id": f"ev_sres_{exec_id[:12]}",
                "evidence_type": "structured_results",
                "run_id": runtime.run_id,
                "status": "VALID",
                "content": {"result_ids": result_ids},
                "supports": list(result_ids),
            }, stage=stage)
            registered.append(f"ev_sres_{exec_id[:12]}")
    except Exception as error:  # noqa: BLE001 - best-effort by design
        # Best effort only; explicit workflow registration remains the
        # authoritative path.  Partial registrations are deterministic-ID
        # and idempotent on retry via the duplicate guard above.  The reason
        # is surfaced to the caller instead of being swallowed, so a silent
        # auto-registration failure can be diagnosed from the run output.
        auto_errors.append(f"{type(error).__name__}: {error}")
    return registered, auto_errors


def _checkpoint_is_fresh(
    runtime, snapshot: dict[str, Any], checkpoint_path: Path
) -> bool:
    """Freshness rule shared by explicit and default checkpoint merging.

    The snapshot hashes the head BEFORE its own CHECKPOINT_CREATED commit,
    so a just-taken checkpoint is always exactly one event ahead.  Accept
    an exact head match, or that single self-referencing tail event;
    anything else is stale.
    """
    if snapshot.get("run_id") != runtime.run_id:
        return False
    head = runtime.ledger.head()
    if snapshot.get("ledger_head_sha256") == head["head_sha256"]:
        return True
    try:
        events = runtime.ledger.read_events()
        tail = events[-1] if events else None
        stored_sequence = int(snapshot.get("ledger_sequence", -1))
        return bool(
            tail is not None
            and int(head["sequence"]) == stored_sequence + 1
            and tail.get("event_type") == "CHECKPOINT_CREATED"
            and str(tail.get("payload", {}).get("checkpoint_path"))
            == checkpoint_path.relative_to(runtime.project_root).as_posix()
        )
    except Exception:  # noqa: BLE001 - unreadable ledger means not fresh
        return False


def _load_mergeable_checkpoint(
    runtime,
) -> tuple[dict[str, Any], Path] | None:
    """Newest-first scan for a mergeable checkpoint of this run.

    Corrupt/foreign/stale entries are skipped silently; `None` means no
    qualifying checkpoint exists (default resume then behaves exactly as
    before this helper existed).
    """
    checkpoints_dir = runtime.project_root / ".mmflow" / "checkpoints"
    if not checkpoints_dir.is_dir():
        return None
    for path in sorted(checkpoints_dir.glob("*.json"), reverse=True):
        try:
            snapshot = read_json_object(path)
        except MMFlowError:
            continue
        if _checkpoint_is_fresh(runtime, snapshot, path):
            return snapshot, path
    return None


def dispatch(args: argparse.Namespace) -> tuple[Any, ExitCode]:
    command = args.command
    # Read-only introspection commands never touch a project or its locks;
    # they resolve policy facts from the skill root so an AI can build
    # registrable payloads without reverse-engineering semantic checkers.
    if command == "schema":
        skill_root = Path(
            getattr(args, "skill_root", None) or installed_skill_root()
        ).resolve(strict=True)
        return (
            _schema_payload(skill_root, getattr(args, "evidence_type", None)),
            ExitCode.OK,
        )
    if command == "adapters":
        skill_root = Path(
            getattr(args, "skill_root", None) or installed_skill_root()
        )
        return _adapters_payload(), ExitCode.OK
    if command == "cookbook":
        skill_root = Path(
            getattr(args, "skill_root", None) or installed_skill_root()
        ).resolve(strict=True)
        return (
            _cookbook_payload(skill_root, getattr(args, "stage", None)),
            ExitCode.OK,
        )
    if command == "figures":
        project = Path(args.project).resolve()
        if args.figures_command == "plan":
            contract = read_json_object(resolve_regular_file_within(project, args.contract))
            from scripts.mmflow_core.figure_plan import build_figure_plan
            # The figure plan is a project artifact.  When this is a live v2
            # project, derive Result IDs from the Registry so every required
            # role is bound to the matching question rather than a global or
            # invented result pool.  A pre-initialization planning workspace
            # deliberately receives an empty snapshot and therefore exposes
            # its missing production evidence instead of fabricating it.
            registry_snapshot: dict[str, Any] = {"results": [], "results_by_question": {}}
            if (project / ".mmflow" / "contract.json").is_file() and (
                project / ".mmflow" / "policy-lock.json"
            ).is_file():
                runtime = load_runtime(project)
                by_question: dict[str, list[str]] = {}
                for record in runtime.registry.iter_latest("result"):
                    payload = record["payload"]
                    question_id = payload.get("question_id")
                    if payload.get("status") == "VALID" and isinstance(question_id, str):
                        by_question.setdefault(question_id, []).append(record["entity_id"])
                registry_snapshot = {
                    "results": sorted(
                        result_id
                        for result_ids in by_question.values()
                        for result_id in result_ids
                    ),
                    "results_by_question": {
                        question_id: sorted(set(result_ids))
                        for question_id, result_ids in sorted(by_question.items())
                    },
                }
            plan = build_figure_plan(contract, registry_snapshot)
            output = project / ".mmflow" / "figure-coverage-plan.json"
            # The plan write mutates project state and therefore holds the
            # single-writer lock like every other mutating transition.
            with _writer_lock(project):
                atomic_write_json(output, plan)
            return plan, ExitCode.OK
        from scripts.mmflow_core.figure_plan import verify_figure_coverage

        plan = read_json_object(resolve_regular_file_within(project, args.plan))
        figures = json.loads(resolve_regular_file_within(project, args.figures).read_text("utf-8"))
        if not isinstance(figures, list):
            raise GateFailedError("figure list must be a JSON array")
        report = verify_figure_coverage(plan, figures)
        return report, ExitCode.OK if report["status"] == "PASS" else ExitCode.GATE_FAILED
    if command == "doctor":
        return doctor(
            args.project,
            probe_write=args.probe_write,
            probe_network=getattr(args, "probe_network", False),
        ), ExitCode.OK
    if command == "migrate":
        # A v1 project is never upgraded in place.  Apply holds both the source
        # writer lock and a destination lock for the whole snapshot/promotion
        # cycle; this prevents source drift and two migrations racing for one
        # destination while retaining a read-only dry-run path.
        root = Path(args.project).resolve()
        if not (root / ".mmflow/contract.json").is_file():
            raise GateFailedError("no project contract present; nothing to migrate")
        if not args.apply:
            contract, plan = _migration_plan(root)
            if (
                int(contract.get("contract_version", 0)) >= 2
                and str(contract.get("skill_version", "")) == "2.0.0"
            ):
                return {"status": "already_v2", "run_id": contract.get("run_id")}, ExitCode.OK
            if args.plan:
                return plan, ExitCode.OK
            raise GateFailedError(
                "migration requires --plan/--dry-run or --apply --output <new_dir>"
            )
        if not isinstance(args.output, str) or not args.output.strip():
            raise GateFailedError("--apply requires --output <new_dir>")
        output = _lexical_absolute(args.output)
        if output == root or root in output.parents:
            raise GateFailedError("migration output must be outside the v1 project")
        _assert_path_chain_safe(output.parent)
        output.parent.mkdir(parents=True, exist_ok=True)
        with _migration_locks(root, output):
            contract, plan = _migration_plan(root)
            if (
                int(contract.get("contract_version", 0)) >= 2
                and str(contract.get("skill_version", "")) == "2.0.0"
            ):
                return {"status": "already_v2", "run_id": contract.get("run_id")}, ExitCode.OK
            if _lexists(output):
                raise GateFailedError(f"migration output already exists: {output}")
            if contract.get("unsupported_future_field") is not None:
                raise GateFailedError("incompatible v1 contract field: unsupported_future_field")
            staging_parent = Path(
                tempfile.mkdtemp(prefix="mmflow-migration-", dir=str(output.parent))
            )
            staging = staging_parent / "project"
            external_backup = output.parent / f"{output.name}.migration-backup-v1"
            staging_output = output.with_name(output.name + ".staging")
            backup_owned = False
            staging_output_owned = False
            try:
                if _lexists(external_backup) or _lexists(staging_output):
                    raise GateFailedError(
                        "migration auxiliary path already exists: "
                        + str(
                            external_backup
                            if _lexists(external_backup)
                            else staging_output
                        )
                    )
                shutil.copytree(
                    root,
                    staging,
                    symlinks=True,
                    ignore=shutil.ignore_patterns(
                        "*.pyc", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "project.lock"
                    ),
                )
                _assert_tree_safe(staging)
                snapshot_sha256 = _tree_sha256(staging)
                if snapshot_sha256 != plan["input_sha256"]:
                    raise IntegrityError("migration source changed while creating the snapshot")
                new_contract = dict(contract)
                new_contract.update(
                    {
                        "contract_version": 2,
                        "skill_version": "2.0.0",
                        "run_id": "run_" + __import__("uuid").uuid4().hex,
                        "migrated_from_run_id": contract.get("run_id"),
                        "migration_status": "REVALIDATION_REQUIRED",
                    }
                )
                atomic_write_json(staging / ".mmflow" / "contract.json", new_contract)
                # Rebuild the immutable ledger and registry.  Historical v1
                # records are retained in an external backup, while the v2
                # project starts with an explicit migration event and no silently
                # trusted evidence; every result/figure/claim must be revalidated.
                mmflow_dir = staging / ".mmflow"
                backup_dir = staging / "migration-backup-v1"
                if (root / ".mmflow").exists():
                    shutil.copytree(
                        root / ".mmflow",
                        backup_dir / ".mmflow",
                        dirs_exist_ok=True,
                        symlinks=True,
                        ignore=shutil.ignore_patterns("project.lock"),
                    )
                for relative in ("events", "registry", "checkpoints"):
                    shutil.rmtree(mmflow_dir / relative, ignore_errors=True)
                for filename in ("ledger-head.json", "ledger-transaction.json", "registry-journal.json"):
                    (mmflow_dir / filename).unlink(missing_ok=True)
                from scripts.mmflow_core.ledger import Ledger

                new_policy = read_json_object(mmflow_dir / "policy-lock.json")
                fresh_ledger = Ledger(staging, new_policy["policy_sha256"])
                fresh_ledger.initialize(new_contract["run_id"])
                fresh_ledger.append(
                    new_contract["run_id"],
                    "PROJECT_CONTRACT_COMMITTED",
                    {"contract_sha256": sha256_bytes(canonical_json_bytes(new_contract))},
                )
                (mmflow_dir / "registry").mkdir(parents=True, exist_ok=True)
                (mmflow_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
                fresh_ledger.append(
                    new_contract["run_id"],
                    "MIGRATION_APPLIED",
                    {
                        "source_run_id": contract.get("run_id"),
                        "source_contract_sha256": hashlib.sha256(
                            json.dumps(contract, sort_keys=True, ensure_ascii=False).encode("utf-8")
                        ).hexdigest(),
                        "revalidation_required": True,
                    },
                )
                report = {
                    **plan,
                    "status": "migration_applied",
                    "output": str(output),
                    "backup": str(external_backup),
                    "v1_complete_mapping": "revalidation_required",
                    "atomic": True,
                }
                # Move the historical backup out of the candidate tree before
                # hashing/reporting.  A later failure removes only paths that
                # this invocation created, never another migration's paths.
                staging.rename(staging_output)
                staging_output_owned = True
                staging_parent.rmdir()
                if (staging_output / "migration-backup-v1").exists():
                    (staging_output / "migration-backup-v1").rename(external_backup)
                    backup_owned = True
                # Complete the report while the project is still in staging.  A
                # report/hash failure must therefore be cleaned up before any
                # externally visible promotion occurs.
                candidate_runtime = load_runtime(staging_output)
                candidate_runtime.registry.validate_integrity()
                # Hash only after every staging mutation (including derived
                # views written by load_runtime) so the reported digest stays
                # verifiable against the promoted tree afterwards.  The report
                # carries its own digest and is excluded from the tree hash.
                report["output_sha256"] = _tree_sha256(
                    staging_output, exclude_relative={".mmflow/migration-report.json"}
                )
                (staging_output / ".mmflow" / "migration-report.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                staging_output.rename(output)
                return report, ExitCode.OK
            except Exception:
                shutil.rmtree(staging_parent, ignore_errors=True)
                if staging_output_owned:
                    shutil.rmtree(staging_output, ignore_errors=True)
                # An auxiliary backup is only committed together with the output.
                # Do not delete a same-named path that predated this invocation.
                if backup_owned and external_backup.exists() and not output.exists():
                    shutil.rmtree(external_backup, ignore_errors=True)
                raise
    if command == "init":
        with _writer_lock(args.project):
            runtime = initialize_project(
                args.project,
                args.competition,
                args.edition,
                quality_profile=args.quality_profile,
            )
        return {
            "run_id": runtime.run_id,
            "policy_sha256": runtime.policy_lock["policy_sha256"],
            "quality_profile": runtime.contract["quality_profile"],
        }, ExitCode.OK

    runtime = load_runtime(args.project)
    if command in MUTATING_COMMANDS:
        with _writer_lock(runtime.project_root, runtime.run_id):
            return _dispatch_locked(runtime, args)
    return _dispatch_locked(runtime, args)


def _dispatch_locked(runtime, args: argparse.Namespace) -> tuple[Any, ExitCode]:
    command = args.command
    _reconcile_for_command(runtime, command)

    controlled_stage = (
        args.stage if command == "run" else FIXED_STAGE_COMMANDS.get(command)
    )
    if controlled_stage is not None:
        _require_active_stage(runtime, controlled_stage)

    if command == "status":
        return runtime.workflow.state(), ExitCode.OK
    if command == "next":
        return next_stage(runtime), ExitCode.OK
    if command == "batch-register":
        batch_obj = read_json_object(resolve_regular_file_within(runtime.project_root, args.file))
        batch = batch_obj.get("entries", [])
        if not isinstance(batch, list):
            raise ConfigError("batch file must contain a JSON array of {kind, payload} entries")
        registered = []
        for i, entry in enumerate(batch):
            kind = entry.get("kind")
            payload = entry.get("payload")
            if not kind or not isinstance(payload, dict):
                raise ConfigError(f"batch[{i}]: missing kind or payload")
            stage = entry.get("stage")
            try:
                record = runtime.registry.register(kind, payload, stage=stage)
                eid = record.get("entity_id") or payload.get(f"{kind}_id", f"entry_{i}")
                registered.append({"kind": kind, "entity_id": str(eid), "status": "OK"})
            except Exception as e:
                # 幂等重试判定按异常类型 + 稳定前缀，而非任意异常消息子串：
                # register 对重复 ID 恒抛 IntegrityError("entity already exists…")，
                # 其余异常一律按真实 ERROR 上报，避免误标 SKIPPED_EXISTING。
                if isinstance(e, IntegrityError) and str(e).startswith("entity already exists"):
                    registered.append({"kind": kind, "entity_id": payload.get(f"{kind}_id", "?"), "status": "SKIPPED_EXISTING", "error": str(e)})
                else:
                    registered.append({"kind": kind, "entity_id": payload.get(f"{kind}_id", "?"), "status": "ERROR", "error": str(e)})
        errors = [r for r in registered if r.get("status") == "ERROR"]
        skipped = [r for r in registered if r.get("status") == "SKIPPED_EXISTING"]
        return {
            "registered": len([r for r in registered if r.get("status") == "OK"]),
            "skipped_existing": len(skipped),
            "errors": len(errors),
            "results": registered,
        }, (
            ExitCode.OK if not errors else ExitCode.GATE_FAILED
        )
    if command == "promote-artifact":
        art = runtime.registry.latest("artifact", args.id)
        if art["payload"].get("status") != "VALID":
            raise IntegrityError(f"artifact {args.id} is not VALID")
        artifact_class = art["payload"].get("artifact_class")
        # promote 只为 production 制品重绑 execution：artifact_class 本身
        # 不可变（demo/external 等类不存在"提升"），非 production 一律拒绝。
        if artifact_class != "production":
            raise GateFailedError(
                f"promote-artifact only rebinds production artifacts; "
                f"{args.id} has class {artifact_class!r}"
            )
        new_payload = dict(art["payload"])
        new_payload["execution_id"] = args.execution_id
        # promote 必须走与 register 相同的载荷校验：伪造/跨运行 execution_id
        # 在此被拒绝，而不是静默写入新版本。
        runtime.registry.validate_payload("artifact", new_payload, resolve_dependencies=True)
        # Re-register with a version bump (same ID, status revision)
        try:
            updated = runtime.registry._write_version(
                "artifact", {**new_payload, "status": "VALID"},
                stage=art.get("created_stage"),
            )
            return {
                "promoted": args.id,
                "artifact_class": new_payload.get("artifact_class"),
                "execution_id": args.execution_id,
                "entity_version": updated.get("entity_version"),
            }, ExitCode.OK
        except IntegrityError as e:
            raise GateFailedError(str(e)) from e
    if command == "export-claims":
        from scripts.mmflow_core.project import export_claims_payload

        payload_out = export_claims_payload(runtime, question=args.question)
        output_path = getattr(args, "output", None)
        if output_path:
            out_path = Path(output_path)
            if out_path.exists():
                raise GateFailedError(f"output already exists: {out_path}")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(payload_out, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return {
                "schema": payload_out["schema"],
                "written": str(out_path),
                "claims": len(payload_out["claims"]),
            }, ExitCode.OK
        return payload_out, ExitCode.OK
    if command == "begin":
        event = runtime.workflow.begin(args.stage)
        return {
            "event_sha256": event["event_sha256"],
            "stage": args.stage,
        }, ExitCode.OK
    if command == "gate":
        state = runtime.workflow.state()
        if state["active_stage"] != args.stage:
            raise GateFailedError("gate target is not the active stage")
        policy = load_policy(runtime, "evidence-v1.json")
        definition = policy.get("stage_requirements", {}).get(args.stage)
        if not isinstance(definition, dict) or not definition.get("evidence_types"):
            raise GateFailedError("stage has no evidence policy")
        engine = GateEngine(
            runtime.project_root,
            runtime.registry,
            policy_version=policy["policy_id"],
        )
        active_redlines = sorted(
            {
                finding["payload"]["redline_id"]
                for finding in runtime.registry.iter_latest("finding")
                if finding["payload"].get("status") == "VALID"
                and finding["payload"].get("finding_status") == "OPEN"
                and finding["payload"].get("redline_id") in policy["redlines"]
            }
        )
        report = engine.run(
            args.stage,
            {
                "required_evidence": definition["evidence_types"],
                "custom_checks": [
                    (
                        definition["semantic_check"],
                        lambda _context: semantic_stage_check(runtime, args.stage),
                    )
                ],
                "active_redlines": active_redlines,
                "current_stage": args.stage,
                "stage_epoch": state["stage_epochs"].get(args.stage),
                "stages_state": state["stages"],
                "cross_stage": policy.get("cross_stage_evidence", {}),
            },
            write_report=True,
        )
        if report["status"] == "BLOCKED":
            block_payload = _block_payload_from_report(report)
            if block_payload is None:
                raise IntegrityError("BLOCKED gate report lacks a structured block payload")
            event = runtime.workflow.block(args.stage, block_payload)
            report["block_event_sha256"] = event["event_sha256"]
            return report, ExitCode.BLOCKED
        runtime.workflow.record_gate(
            args.stage, report, report["evidence_fingerprint"]
        )
        if report["status"] == "PASS":
            return report, ExitCode.OK
        if report["status"] == "ERROR":
            return report, ExitCode.INTERNAL
        return report, ExitCode.GATE_FAILED
    if command == "advance":
        state = runtime.workflow.state()
        stage = state["active_stage"]
        if stage is None:
            raise GateFailedError("no active stage")
        policy = load_policy(runtime, "evidence-v1.json")
        fingerprint = evidence_fingerprint(
            runtime.registry, stage, policy["policy_id"]
        )
        event = runtime.workflow.advance(fingerprint)
        return {
            "event_sha256": event["event_sha256"],
            "state": runtime.workflow.state(),
        }, ExitCode.OK
    if command == "rollback":
        invalidate_stage_downstream(
            runtime.registry,
            args.stage,
            f"rollback to {args.stage}: {args.reason}",
        )
        event = runtime.workflow.rollback(args.stage, args.reason)
        return {
            "event_sha256": event["event_sha256"],
            "state": runtime.workflow.state(),
        }, ExitCode.OK
    if command == "register-input":
        source = resolve_regular_file_within(runtime.project_root, args.path)
        relative = source.relative_to(runtime.project_root).as_posix()
        state = runtime.workflow.state()
        payload = {
            "artifact_id": args.id,
            "artifact_class": "external",
            "artifact_type": args.type,
            "run_id": runtime.run_id,
            "status": "VALID",
            "relative_path": relative,
            "sha256": sha256_file(source),
            "size_bytes": source.stat().st_size,
            "inputs": [],
        }
        return runtime.registry.register(
            "artifact", payload, stage=state.get("active_stage")
        ), ExitCode.OK
    if command == "invalidate":
        registry = runtime.registry
        graph = LineageGraph(registry)
        affected = graph.invalidate_from(
            [args.id], args.reason, root_status="INVALID"
        )
        rollback_stage = graph.earliest_affected_stage(affected)
        if rollback_stage is not None:
            invalidate_stage_downstream(
                registry, rollback_stage, f"invalidate {args.id}: {args.reason}"
            )
            runtime.workflow.rollback(
                rollback_stage, f"invalidate {args.id}: {args.reason}"
            )
        return {
            "root": args.id,
            "affected": affected,
            "rollback_stage": rollback_stage,
            "rerun_scope": rerun_scope_from(rollback_stage),
        }, ExitCode.OK
    if command == "retire-artifact":
        # 代际重建专用维护入口：把上一代固定路径制品标记 STALE 并沿血缘
        # 传播，但【不】自动回退阶段——是否回退、回退到哪由调用方依据
        # suggested_rollback_stage 显式执行 rollback（cookbook 代际纪律 2）。
        registry = runtime.registry
        graph = LineageGraph(registry)
        ident = registry._committed_identity_map()
        if args.id not in ident:
            raise ConfigError(f"unknown entity id: {args.id}")
        affected = graph.invalidate_from([args.id], args.reason, root_status="STALE")
        suggested = graph.earliest_affected_stage(affected)
        return {
            "root": args.id,
            "root_status": "STALE",
            "affected": affected,
            "suggested_rollback_stage": suggested,
            "rerun_scope": rerun_scope_from(suggested),
            "next_step": (
                f"review rerun_scope, then run: mmflow rollback "
                f"{suggested} --reason <...> (only if the retired generation "
                f"supported passed gates)"
                if suggested is not None
                else "no stage impact; re-register the new generation"
            ),
        }, ExitCode.OK
    if command == "close-finding":
        closure_path = resolve_regular_file_within(
            runtime.project_root, args.closure
        )
        closure = read_json_object(closure_path)
        return runtime.registry.close_finding(
            args.id, closure, args.reason, mode=args.mode
        ), ExitCode.OK
    if command == "scan-privacy":
        manifest_path = resolve_regular_file_within(
            runtime.project_root, args.manifest
        )
        manifest = read_json_object(manifest_path)
        report = scan_manifest_files(runtime, manifest.get("files"))
        requested = Path(args.output)
        output_path = resolve_within(
            runtime.project_root,
            requested if requested.is_absolute() else runtime.project_root / requested,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            if getattr(args, "force_new_name", False):
                stem, suffix = output_path.stem, output_path.suffix
                counter = 1
                while True:
                    candidate = output_path.with_name(f"{stem}-{counter}{suffix}")
                    if not candidate.exists():
                        output_path = candidate
                        break
                    counter += 1
            else:
                raise IntegrityError(
                    "privacy scan output already exists; outputs are immutable"
                    " (retry with --force-new-name to auto-number)"
                )
        atomic_write_json(output_path, report)
        return {
            "status": report["status"],
            "output": output_path.relative_to(runtime.project_root).as_posix(),
            "findings": sum(
                len(file["findings"]) for file in report["files"]
            ),
        }, ExitCode.OK if report["status"] == "PASS" else ExitCode.GATE_FAILED
    if command == "release-status":
        try:
            runtime.registry.validate_integrity()
            runtime.ledger.validate()
            integrity_ok = True
        except IntegrityError:
            integrity_ok = False
        label = compute_release_label(runtime, integrity_ok=integrity_ok)
        label["policy_version"] = load_policy(runtime, "evidence-v1.json")["policy_id"]
        return label, ExitCode.OK
    if command in REGISTER_KINDS:
        return _register_payload(
            runtime, REGISTER_KINDS[command], args.file
        ), ExitCode.OK
    if command == "run":
        config_path = resolve_regular_file_within(runtime.project_root, args.config)
        spec = read_json_object(config_path)
        program = list(args.program)
        if program and program[0] == "--":
            program = program[1:]
        if not program:
            raise GateFailedError("run requires a program after --")
        request = ExecutionRequest(
            stage=args.stage,
            question=args.question,
            role=args.role,
            artifact_class=args.artifact_class,
            command=program,
            input_paths=list(spec.get("input_paths", [])),
            code_paths=list(spec.get("code_paths", [])),
            config_paths=list(spec.get("config_paths", [])),
            source_artifact_ids=list(spec.get("source_artifact_ids", [])),
            expected_outputs=list(spec.get("expected_outputs", [])),
            comparison_policies=dict(spec.get("comparison_policies", {})),
            dataset_split_ids=list(spec.get("dataset_split_ids", [])),
            random_protocol=dict(spec.get("random_protocol", {})),
            timeout_seconds=int(spec.get("timeout_seconds", 3600)),
            output_encoding=spec.get("output_encoding"),
            environment=dict(spec.get("environment", {})),
        )
        result = ExecutionRunner(
            runtime.project_root,
            runtime.ledger,
            runtime.registry,
            runtime.run_id,
        ).execute(request)
        exec_payload = result.execution["payload"]
        code = (
            ExitCode.OK
            if exec_payload["status"] == "VALID"
            else ExitCode.GATE_FAILED
        )

        auto_evidence = []
        auto_evidence_errors: list[str] = []
        if exec_payload["status"] == "VALID":
            auto_evidence, auto_evidence_errors = _autoregister_run_evidences(
                runtime, args.stage, exec_payload, result)
        return {
            "execution": result.execution,
            "artifacts": result.artifacts,
            "auto_evidence": auto_evidence,
            "auto_evidence_errors": auto_evidence_errors,
        }, code
    if command == "render-bindings":
        source_path = resolve_regular_file_within(
            runtime.project_root, args.source
        )
        manifest = render_project_latex_bindings(
            source_path,
            runtime.registry,
            runtime.project_root,
            args.output,
        )
        return {
            "bindings": manifest["binding_count"],
            "output": str(Path(args.output)),
            "sha256": manifest["rendered_sha256"],
            "characters": resolve_regular_file_within(
                runtime.project_root,
                args.output,
            ).read_text("utf-8").__len__(),
            "source_closure": manifest["source_closure"],
            "rendered_source_closure": manifest["rendered_source_closure"],
        }, ExitCode.OK
    if command == "scan-manuscript":
        source_path = resolve_regular_file_within(
            runtime.project_root, args.source
        )
        closure = scan_project_latex_sources(runtime.project_root, source_path)
        hits = closure["hits"]
        return {
            "status": "PASS" if not hits else "FAIL",
            "hits": hits,
            "sources": closure["sources"],
        }, ExitCode.OK if not hits else ExitCode.GATE_FAILED
    if command == "reproduce":
        runner = ExecutionRunner(
            runtime.project_root,
            runtime.ledger,
            runtime.registry,
            runtime.run_id,
        )
        try:
            reproduced = runner.reproduce(args.execution)
        except IntegrityError as error:
            # Cannot reproduce (e.g. sources changed): per the acceptance
            # contract the workflow auto-invalidates the original execution,
            # makes downstream STALE and rolls back to the earliest affected
            # stage instead of leaving a broken P9 claim in place.
            graph = LineageGraph(runtime.registry)
            affected = graph.invalidate_from(
                [args.execution], f"cannot reproduce: {error}", root_status="INVALID"
            )
            rollback_stage = graph.earliest_affected_stage(affected) or "P5"
            invalidate_stage_downstream(
                runtime.registry,
                rollback_stage,
                f"cannot reproduce {args.execution}: {error}",
            )
            runtime.workflow.rollback(
                rollback_stage, f"cannot reproduce {args.execution}"
            )
            return {
                "outcome": "FAIL",
                "reason": str(error),
                "affected": affected,
                "rollback_stage": rollback_stage,
                "rerun_scope": rerun_scope_from(rollback_stage),
            }, ExitCode.GATE_FAILED
        report = runner.compare_reproduction(args.execution, reproduced)
        report_path = (
            runtime.project_root
            / ".mmflow/reports"
            / f"reproduction_{args.execution}_{reproduced.execution['entity_id']}.json"
        )
        atomic_write_json(report_path, report)
        return report, (
            ExitCode.OK
            if report["outcome"] == "PASS"
            else ExitCode.INTERNAL
            if report["outcome"] == "ERROR"
            else ExitCode.GATE_FAILED
        )
    if command == "review":
        source_path = resolve_regular_file_within(
            runtime.project_root, args.file
        )
        try:
            source = json.loads(source_path.read_text("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise GateFailedError("cannot read review JSON") from error
        if not isinstance(source, list):
            raise GateFailedError("review file must be a JSON list")
        state = runtime.workflow.state()
        records = [
            runtime.registry.register(
                "finding", {**item, "run_id": runtime.run_id}, stage=state["active_stage"]
            )
            for item in source
        ]
        return {
            "registered": [record["entity_id"] for record in records]
        }, ExitCode.OK
    if command == "audit":
        report = run_domain_audit(runtime)
        return report, (
            ExitCode.OK if report["status"] in {"PASS", "NOT_APPLICABLE"} else ExitCode.GATE_FAILED
        )
    if command == "checkpoint":
        return create_checkpoint(runtime), ExitCode.OK
    if command == "resume":
        if args.resolve_blocked:
            state = runtime.workflow.state()
            block_sequence = (
                int(state["blocked"]["event_sequence"])
                if isinstance(state.get("blocked"), dict)
                else None
            )

            def validate_resolution_evidence(evidence_id: str, block_event_sequence: int) -> None:
                record = runtime.registry.find_entity(evidence_id)
                if record["entity_kind"] != "evidence":
                    raise IntegrityError(
                        f"resolution evidence must be an evidence entity: {evidence_id}"
                    )
                payload = record["payload"]
                if payload.get("status") != "VALID":
                    raise IntegrityError(
                        f"resolution evidence is not current and valid: {evidence_id}"
                    )
                created_sequence = int(record.get("created_ledger_sequence", 0))
                if created_sequence <= block_event_sequence:
                    raise IntegrityError(
                        f"resolution evidence predates the block event: {evidence_id}"
                    )

            runtime.workflow.resume_blocked(
                list(args.evidence or []), validate_resolution_evidence
            )
        state_view = runtime.workflow.state()
        next_action = next_stage(runtime)
        payload: dict[str, Any] = {"state": state_view, "next": next_action}
        if getattr(args, "from_checkpoint", None):
            checkpoint_path = resolve_regular_file_within(
                runtime.project_root, args.from_checkpoint
            )
            snapshot = read_json_object(checkpoint_path)
            if snapshot.get("run_id") != runtime.run_id:
                raise IntegrityError(
                    "checkpoint belongs to another run; refusing to merge"
                )
            if not _checkpoint_is_fresh(runtime, snapshot, checkpoint_path):
                raise IntegrityError(
                    "checkpoint predates or postdates the current ledger "
                    "head; re-run `checkpoint` instead of merging a "
                    "stale one"
                )
            # 账本重放仍是事实源；checkpoint 仅提供恢复辅助队列。
            payload["checkpoint_work_queue"] = snapshot.get("work_queue")
            payload["checkpoint_created_at"] = snapshot.get("created_at")
        else:
            # M-R6: default resume opportunistically merges the newest
            # mergeable checkpoint (silent skip when none qualifies), so
            # SKILL.md's checkpoint-before-long-stage guidance pays off
            # without an extra flag.  The ledger replay stays the source
            # of truth either way.
            merged = _load_mergeable_checkpoint(runtime)
            if merged is not None:
                snapshot, path = merged
                payload["checkpoint_work_queue"] = snapshot.get("work_queue")
                payload["checkpoint_created_at"] = snapshot.get("created_at")
                payload["checkpoint_used"] = path.relative_to(
                    runtime.project_root
                ).as_posix()
        return payload, ExitCode.OK
    if command == "package":
        return create_delivery_archive(
            runtime, args.manifest, args.output, args.candidate,
            force_new_name=getattr(args, "force_new_name", False),
        ), ExitCode.OK
    raise GateFailedError(f"unsupported command: {command}")


def _scan_v1_registry(root: Path) -> list[dict[str, Any]]:
    """Read a v1 project's registry records without loading the v2 runtime."""
    records: list[dict[str, Any]] = []
    registry_root = root / ".mmflow/registry"
    if not registry_root.is_dir():
        return records
    for path in sorted(registry_root.rglob("*.json")):
        try:
            value = json.loads(path.read_text("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("entity_kind") == "evidence":
            records.append(value)
    return records


def _harden_console() -> None:
    # Legacy consoles (e.g. GBK) cannot encode some report glyphs; degrade
    # those characters instead of crashing an otherwise successful command.
    # JSON mode already emits pure ASCII, so programmatic consumers are unaffected.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (OSError, ValueError):
                pass


def main() -> int:
    _harden_console()
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload, code = dispatch(args)
        if code in (ExitCode.OK, ExitCode.GATE_FAILED):
            try:
                from scripts.mmflow_core.project import (
                    refresh_last_loaded_integrity_cache,
                )

                refresh_last_loaded_integrity_cache()
            except Exception:
                pass
        _emit(payload, args.json)
        return int(code)
    except MMFlowError as error:
        _emit(
            {"error_type": type(error).__name__, "message": str(error)},
            args.json,
        )
        return int(error.exit_code)
    except Exception as error:
        _emit(
            {"error_type": type(error).__name__, "message": str(error)},
            args.json,
        )
        return int(ExitCode.INTERNAL)


if __name__ == "__main__":
    raise SystemExit(main())
