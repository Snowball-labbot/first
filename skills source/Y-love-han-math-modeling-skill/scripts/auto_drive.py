# -*- coding: utf-8 -*-
"""auto_drive.py — P0→P11 计划驱动参考编排器（extended-sprint-protocol 参考节）。

用途：按固定步骤序列驱动 mmflow CLI 完成"程序可判定"的流程转换；
每步先 gate 后 advance，FAIL/BLOCKED 即带非零退出码停止，不静默跳过。
专业工作（建模、登记载荷、论文写作）不由编排器代做：全部赛题相关
内容放在项目内 autodrive/plan.json 的 CONTENT 区，由执行方按赛题替换。

用法：
  python scripts/auto_drive.py <project_root> <gen_tag> [step ...]

前置条件：
  先人工运行 `mmflow init --competition ... --edition ...`（赛事名称与届次
  是用户事实，编排器不代填）。autodrive/plan.json 必须已创建（schema:
  mmflow-autodrive-plan/v1，content 区可留待填充；p11 区提供交付路径）。

步骤语义（缺省序列 p0→…→p11(prep/pack/scan/ev)→finish）：
  p0..p10   对每个阶段：需要时 begin → gate → PASS 则 advance；
            FAIL/BLOCKED 停止（退出码取自子进程，非零）。
  p11-prep  进入 P11 并用 next 提示缺失证据（交付清单等由执行方登记）。
  p11-pack  package --candidate（路径取自 plan.p11）。
  p11-scan  scan-privacy（路径取自 plan.p11）。
  p11-ev    gate p11 → PASS 则 advance（COMPLETE）→ final package →
            release-status 终核。
  finish    audit + release-status，输出程序计算的标签。

约定：
  - 所有状态转换经官方 CLI 子进程执行（子进程内部持有单写者锁）；
  - 编排器自身不写任何项目状态，只读 status/next/plan.json 并写
    autodrive/<gen_tag>/steps.log 供人工审计；
  - plan.json 的 gen_tag 与命令行 gen_tag 一致才执行（防跑陈旧计划）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
MMFLOW = SCRIPT_DIR / "mmflow.py"

DEFAULT_STEPS = (
    [f"p{i}" for i in range(11)]
    + ["p11-prep", "p11-pack", "p11-scan", "p11-ev", "finish"]
)
PLAN_SCHEMA = "mmflow-autodrive-plan/v1"


def _log(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "steps.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run_cli(project: Path, *args: str) -> tuple[int, dict | None, str]:
    completed = subprocess.run(
        [sys.executable, str(MMFLOW), *args, "--project", str(project), "--json"],
        capture_output=True, text=True,
    )
    parsed = None
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        pass
    return completed.returncode, parsed, (completed.stderr or completed.stdout)[-400:]


def _stage_status(state: dict, stage: str) -> str | None:
    stages = state.get("stages") or {}
    entry = stages.get(stage)
    if isinstance(entry, dict):
        return entry.get("status")
    return entry


def _run_stage_step(project: Path, step: str, run_dir: Path) -> int:
    stage = step.upper() if step.startswith("p") and len(step) == 2 else step
    code, state, err = _run_cli(project, "status")
    if code != 0 or not isinstance(state, dict):
        print(f"[{step}] status failed: {err}")
        return code or 1
    status = _stage_status(state, stage)
    if status == "PASSED":
        print(f"[{step}] already PASSED; skip")
        _log(run_dir, {"step": step, "result": "SKIP_PASSED"})
        return 0
    if status != "ACTIVE":
        code, begun, err = _run_cli(project, "begin", stage)
        if code != 0:
            print(f"[{step}] begin {stage} failed: {err}")
            _log(run_dir, {"step": step, "result": "BEGIN_FAIL", "stderr": err})
            return code or 1
        _log(run_dir, {"step": step, "result": "BEGUN"})
    code, gate, err = _run_cli(project, "gate", stage)
    _log(run_dir, {"step": step, "result": "GATE", "returncode": code})
    if code != 0:
        print(f"[{step}] gate {stage} FAILED/BLOCKED: {err}")
        return code or 1
    code, advanced, err = _run_cli(project, "advance")
    if code != 0:
        print(f"[{step}] advance failed: {err}")
        _log(run_dir, {"step": step, "result": "ADVANCE_FAIL", "stderr": err})
        return code or 1
    print(f"[{step}] advanced")
    _log(run_dir, {"step": step, "result": "ADVANCED"})
    return 0


def _plan_paths(plan: dict) -> dict:
    p11 = plan.get("p11") or {}
    for key in ("manifest", "candidate_package", "privacy_scan", "final_package"):
        if not p11.get(key):
            raise SystemExit(
                f"plan.p11.{key} missing; add delivery paths to autodrive/plan.json"
            )
    return p11


def _run_custom_step(project: Path, step: str, run_dir: Path, plan: dict) -> int:
    if step == "p11-prep":
        code, state, err = _run_cli(project, "status")
        if code != 0 or not isinstance(state, dict):
            print(f"[{step}] status failed: {err}")
            return code or 1
        status = _stage_status(state, "P11")
        if status not in ("ACTIVE", "PASSED"):
            code, _begun, err = _run_cli(project, "begin", "P11")
            if code != 0:
                print(f"[{step}] begin P11 failed: {err}")
                return code or 1
        code, nxt, err = _run_cli(project, "next")
        print(f"[{step}] P11 active; next hint: missing evidence per `next` output")
        _log(run_dir, {"step": step, "result": "PREP", "next_hint_available": code == 0})
        return 0
    paths = _plan_paths(plan)
    if step == "p11-pack":
        code, _out, err = _run_cli(
            project, "package", "--manifest", paths["manifest"],
            "--output", paths["candidate_package"], "--candidate",
        )
        _log(run_dir, {"step": step, "result": "PACK", "returncode": code})
    elif step == "p11-scan":
        code, _out, err = _run_cli(
            project, "scan-privacy", "--manifest", paths["manifest"],
            "--output", paths["privacy_scan"], "--force-new-name",
        )
        _log(run_dir, {"step": step, "result": "SCAN", "returncode": code})
    elif step == "p11-ev":
        code, gate, err = _run_cli(project, "gate", "P11")
        _log(run_dir, {"step": step, "result": "GATE", "returncode": code})
        if code != 0:
            print(f"[{step}] gate P11 FAILED/BLOCKED: {err}")
            return code or 1
        code, _out, err = _run_cli(project, "advance")
        if code != 0:
            print(f"[{step}] advance failed: {err}")
            return code or 1
        code, _out, err = _run_cli(
            project, "package", "--manifest", paths["manifest"],
            "--output", paths["final_package"],
        )
        if code != 0:
            print(f"[{step}] final package failed: {err}")
            return code or 1
        code, label, err = _run_cli(project, "release-status")
        print(f"[{step}] release-status -> "
              f"{json.dumps(label, ensure_ascii=False)[:200] if label else err}")
        _log(run_dir, {"step": step, "result": "EV", "returncode": code})
    elif step == "finish":
        code, _out, err = _run_cli(project, "audit")
        if code != 0:
            print(f"[{step}] audit failed: {err}")
            return code or 1
        code, label, err = _run_cli(project, "release-status")
        print(f"[{step}] final label: "
              f"{json.dumps(label, ensure_ascii=False)[:200] if label else err}")
        _log(run_dir, {"step": step, "result": "FINISH", "returncode": code})
    else:
        print(f"unknown step: {step}")
        return 2
    if code != 0:
        return code or 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan-driven reference orchestrator for the P0-P11 workflow"
    )
    parser.add_argument("project_root")
    parser.add_argument("gen_tag", help="generation tag; must match plan.json gen_tag")
    parser.add_argument("steps", nargs="*",
                        help="subset of steps (default: full p0..p11+finish sequence)")
    args = parser.parse_args(argv)

    project = Path(args.project_root).resolve()
    if not (project / ".mmflow" / "contract.json").is_file():
        print("error: project not initialized; run `mmflow init --competition ... "
              "--edition ...` first (user facts are not auto-filled)")
        return 2
    plan_path = project / "autodrive" / "plan.json"
    if not plan_path.is_file():
        print(f"error: plan not found: {plan_path}")
        return 2
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("schema") != PLAN_SCHEMA:
        print(f"error: plan schema must be {PLAN_SCHEMA}")
        return 2
    if plan.get("gen_tag") and plan["gen_tag"] != args.gen_tag:
        print(f"error: plan gen_tag {plan['gen_tag']!r} != CLI gen_tag {args.gen_tag!r}")
        return 2
    steps = args.steps or list(DEFAULT_STEPS)
    run_dir = project / "autodrive" / args.gen_tag
    for step in steps:
        if step in ("p11-prep", "p11-pack", "p11-scan", "p11-ev", "finish"):
            code = _run_custom_step(project, step, run_dir, plan)
        else:
            code = _run_stage_step(project, step, run_dir)
        if code != 0:
            print(f"stopped at step {step} with exit code {code}; "
                  f"resolve the root cause, then re-run from this step")
            return code
    print(json.dumps({"status": "OK", "steps": steps,
                      "log": str(run_dir / "steps.log")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
