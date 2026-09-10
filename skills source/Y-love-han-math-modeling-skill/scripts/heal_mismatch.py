# -*- coding: utf-8 -*-
"""heal_mismatch.py — 内容漂移（monotonic IntegrityError）恢复维护入口。

对"内容已变的 VALID artifact 根"做秩守卫失效并回退到最早受影响阶段，
用于从 monotonic IntegrityError 中恢复。这是 workflow-contract.md
"命令生命周期"中登记的维护工具；它只做失效与回退，绝不改写任何
实体状态字段或哈希，也不删除失败痕迹。

用法：
  python scripts/heal_mismatch.py --project <root> [artifact_id ...] [--json]
  python scripts/heal_mismatch.py --project <root>            # 扫描全部 VALID artifact

行为：
  1. 持项目单写者锁执行；
  2. 给定 artifact_id 列表时逐个"秩守卫"核验：必须是当前 VALID、
     且磁盘内容与登记哈希确实不一致的"根"；未漂移的条目报告 SKIP；
  3. 不给参数时等价于全量 reconcile（扫描全部 VALID artifact）；
  4. 对确认漂移的根沿血缘做 INVALID 失效传播，按受影响实体溯源
     （created_stage / execution.stage）回退最早受影响阶段并使下游失效；
  5. 输出 JSON 报告：changed / skipped / affected / rollback_stage。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SKILL_ROOT))

from scripts.mmflow_core.canonical import resolve_within  # noqa: E402
from scripts.mmflow_core.errors import ConfigError, IntegrityError  # noqa: E402
from scripts.mmflow_core.canonical import sha256_file  # noqa: E402
from scripts.mmflow_core.lineage import (  # noqa: E402
    LineageGraph,
    invalidate_stage_downstream,
)
from scripts.mmflow_core.locking import ProjectLock  # noqa: E402
from scripts.mmflow_core.project import load_runtime  # noqa: E402


def _drifted_ids(runtime, requested: list[str] | None) -> tuple[list[str], list[str]]:
    """返回 (确认漂移的根, 未漂移跳过的根)。秩守卫：只认"磁盘内容 ≠ 登记哈希"
    的 VALID artifact 为根；请求中其余条目一律 SKIP，不做传播。"""
    changed: list[str] = []
    skipped: list[str] = []
    if requested is not None:
        for artifact_id in requested:
            try:
                record = runtime.registry.latest("artifact", artifact_id)
            except IntegrityError:
                raise ConfigError(f"unknown artifact: {artifact_id}")
            payload = record["payload"]
            if payload.get("status") != "VALID":
                skipped.append(artifact_id)
                continue
            path = resolve_within(
                runtime.project_root,
                runtime.project_root / payload["relative_path"],
                must_exist=False,
            )
            if (
                not path.is_file()
                or path.is_symlink()
                or sha256_file(path) != payload["sha256"]
            ):
                changed.append(artifact_id)
            else:
                skipped.append(artifact_id)
        return changed, skipped
    for record in runtime.registry.iter_latest("artifact"):
        payload = record["payload"]
        if payload.get("status") != "VALID":
            continue
        path = resolve_within(
            runtime.project_root,
            runtime.project_root / payload["relative_path"],
            must_exist=False,
        )
        if (
            not path.is_file()
            or path.is_symlink()
            or sha256_file(path) != payload["sha256"]
        ):
            changed.append(record["entity_id"])
    return changed, skipped


def _rollback_stage(runtime, affected: list[str], graph: LineageGraph) -> str | None:
    state = runtime.workflow.state()
    reached = {
        stage
        for stage, status in state["stages"].items()
        if status != "NOT_STARTED"
    }
    candidates: list[str] = []
    for entity_id in affected:
        kind = graph.kind_by_id[entity_id]
        record = runtime.registry.latest(kind, entity_id)
        payload = record["payload"]
        stage = record.get("created_stage")
        if kind == "execution":
            stage = payload.get("stage")
        if isinstance(stage, str) and stage in reached:
            candidates.append(stage)
    if not candidates:
        return None
    return min(candidates, key=lambda stage: int(stage[1:]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Heal artifact content drift: invalidate drifted roots and roll back"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("artifact_ids", nargs="*", help="drifted artifact roots (empty = scan all)")
    parser.add_argument("--reason", default="artifact content changed (manual heal entry)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project).resolve()
    if not (project_root / ".mmflow" / "contract.json").is_file():
        print(json.dumps({"status": "FAIL",
                          "error": "not an initialized mmflow project"}))
        return 2
    runtime = load_runtime(project_root)
    lock = ProjectLock(runtime.project_root, runtime.run_id)
    lock.acquire()
    try:
        changed, skipped = _drifted_ids(
            runtime, list(args.artifact_ids) if args.artifact_ids else None
        )
        report: dict[str, object] = {
            "status": "OK",
            "changed": sorted(changed),
            "skipped": sorted(skipped),
            "affected": [],
            "rollback_stage": None,
            "rolled_back": False,
        }
        if changed:
            graph = LineageGraph(runtime.registry)
            affected = graph.invalidate_from(changed, args.reason, root_status="INVALID")
            report["affected"] = sorted(affected)
            rollback = _rollback_stage(runtime, affected, graph)
            report["rollback_stage"] = rollback
            if rollback is not None:
                state = runtime.workflow.state()
                if state["stages"].get(rollback) not in (None, "NOT_STARTED"):
                    invalidate_stage_downstream(
                        runtime.registry, rollback,
                        "artifact hash changed; downstream evidence invalidated",
                    )
                    runtime.workflow.rollback(
                        rollback,
                        "artifact hash changed; downstream evidence invalidated",
                    )
                    report["rolled_back"] = True
        print(json.dumps(report, ensure_ascii=False))
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
