# -*- coding: utf-8 -*-
"""
generate_all.py — 声明式批量出图驱动器（P8 图表生产）
用途：从一份声明式图表计划一次产出全部 PNG + sidecar 对。
      计划中的每个 item 指定 role（可视化模板名）与 data（生产图输入）；
      本脚本只做批量调度与汇总报告，不生成任何数据、不改写任何数值。

计划 schema: mmflow-figure-plan-input/v1
{
  "schema": "mmflow-figure-plan-input/v1",
  "items": [
    {
      "role": "heatmap",                  // 模板名（下表之一）
      "data": { ...该模板的生产图输入... } // 必含 question_id/input_artifact_ids/
                                            // input_sha256/units/sample_size
    }
  ]
}

支持 role ↔ 模板：architecture, bar_chart, convergence, data_overview,
data_processing, distribution, heatmap, model_diagram, model_result,
network_graph, pareto, radar, residual_diagnosis, result_table,
sensitivity, spatial_map, scatter_fit, validation

运行方式：python generate_all.py --plan plan.json --out-dir figures [--only heatmap,radar]
输出：<out-dir>/每 role 一对 PNG + sidecar.json；generation_report.json
退出码：0 全部成功；1 存在失败项（失败不阻断其余条目，逐项回报）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLAN_SCHEMA = "mmflow-figure-plan-input/v1"


def _load_modules():
    """同目录可视化模板导入：优先包内相对导入，失败时按文件路径松散加载。"""
    modules = {}
    names = [
        "architecture", "bar_chart", "convergence", "data_overview",
        "data_processing", "distribution", "heatmap", "model_diagram",
        "model_result", "network_graph", "pareto", "radar",
        "residual_diagnosis", "result_table", "sensitivity", "spatial_map",
        "scatter_fit", "validation",
    ]
    here = Path(__file__).resolve().parent
    try:
        package = __import__(__package__ or "visualization", fromlist=names)
        for name in names:
            modules[name] = getattr(package, name)
        return modules
    except ImportError:
        pass
    import importlib.util

    here_text = str(here)
    if here_text not in sys.path:
        # 松散加载时兄弟模块使用 `from plotting_common import ...` 回退，
        # 必须保证模板目录本身可导入
        sys.path.insert(0, here_text)
    for name in names:
        path = here / f"{name}.py"
        if not path.is_file():
            raise SystemExit(f"missing sibling template: {path}")
        spec = importlib.util.spec_from_file_location(
            f"mmflow_visualization_{name}", path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    return modules


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Batch-generate production figures from a declarative plan")
    parser.add_argument("--plan", required=True, help="figure plan JSON (mmflow-figure-plan-input/v1)")
    parser.add_argument("--out-dir", required=True, help="output directory for PNG + sidecar pairs")
    parser.add_argument("--only", default=None, help="逗号分隔的 role 白名单；缺省全部执行")
    args = parser.parse_args(argv)

    plan_path = Path(args.plan)
    if not plan_path.is_file():
        print(f"plan not found: {plan_path}")
        return 2
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("schema") != PLAN_SCHEMA:
        print(f"plan schema must be {PLAN_SCHEMA}; got {plan.get('schema')!r}")
        return 2
    items = plan.get("items")
    if not isinstance(items, list) or not items:
        print("plan.items must be a non-empty list")
        return 2
    only = {item.strip() for item in args.only.split(",")} if args.only else None
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    modules = _load_modules()

    report = {"schema": "mmflow-figure-generation-report/v1", "results": []}
    failures = 0
    for index, item in enumerate(items):
        role = str(item.get("role", ""))
        entry = {"index": index, "role": role}
        if only is not None and role not in only:
            entry["status"] = "SKIPPED"
            report["results"].append(entry)
            continue
        module = modules.get(role)
        if module is None or not hasattr(module, "generate"):
            entry["status"] = "ERROR"
            entry["error"] = f"unknown role: {role}"
            failures += 1
            report["results"].append(entry)
            continue
        try:
            produced = module.generate(item.get("data"), out_dir)
            entry["status"] = "OK"
            entry["image_path"] = produced["image_path"]
            entry["sidecar_path"] = produced["sidecar_path"]
        except Exception as error:  # 单条失败不阻断其余条目
            entry["status"] = "ERROR"
            entry["error"] = f"{type(error).__name__}: {error}"
            failures += 1
        report["results"].append(entry)
    report["total"] = len(items)
    report["ok"] = sum(1 for r in report["results"] if r["status"] == "OK")
    report["errors"] = failures
    report_path = out_dir / "generation_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"report": str(report_path), "ok": report["ok"], "errors": failures},
                     ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
