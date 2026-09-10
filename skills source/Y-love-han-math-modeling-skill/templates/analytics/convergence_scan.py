# -*- coding: utf-8 -*-
"""
convergence_scan.py — 步长收敛扫描（ODE/PDE 适配器的收敛判定实现）
用途：对"步长 h -> 解标量 Q(h)"的映射执行步长减半扫描、逐级差分与
      Richardson 观测收敛阶估计，并按预登记容差判定收敛。
      只依赖标准库，可在无 numpy 环境直接运行。
定位：判定工具。解算子由项目按题目提供（--map 脚本或直接喂 Q 序列），
      本脚本不实现任何具体方程求解。

输入 JSON（--input）字段：
{
  "steps":  [0.1, 0.05, 0.025, 0.0125],   // 显式步长序列（可省略，
                                           // 省略时由 h0 与 levels 自动减半生成）
  "values": [1.0243, 1.0061, 1.0015, 1.0004],
  "tolerance": 1e-3,                        // 预登记收敛容差（相邻差分）
  "expected_order": 2                       // 可选：理论收敛阶（Richardson 对照）
}
或提供 --map "python solve.py"（从 stdin 读 h，stdout 输出 Q(h)），
由本脚本执行步长减半扫描后同样进入差分与判定流程。

运行方式：python convergence_scan.py --input conv.json --output conv_report.json
退出码：0 收敛判定 PASS；1 判定 FAIL；2 输入不合法
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _fail(message: str) -> None:
    print(f"error: {message}")
    sys.exit(2)


def richardson_orders(steps, values):
    """逐级差分与 Richardson 观测阶：p_k = ln(d_{k-1}/d_k) / ln(r)，
    其中 d_k = |Q_{k+1} - Q_k|，r 为相邻步长比。"""
    diffs = [
        abs(values[i + 1] - values[i])
        for i in range(len(values) - 1)
    ]
    orders = []
    for i in range(1, len(diffs)):
        if diffs[i] > 0 and diffs[i - 1] > 0:
            ratio = steps[i + 1] / steps[i]
            if ratio > 0 and not math.isclose(ratio, 1.0):
                orders.append(math.log(diffs[i - 1] / diffs[i]) / math.log(1.0 / ratio))
    return diffs, orders


def scan_with_map(command, h0: float, levels: int):
    steps = [h0 / (2 ** level) for level in range(levels)]
    values = []
    for step in steps:
        completed = subprocess.run(
            command, input=f"{step!r}\n", capture_output=True,
            text=True, shell=True, timeout=300,
        )
        if completed.returncode != 0:
            _fail(f"map command failed at h={step}: {completed.stderr.strip()[:200]}")
        values.append(float(completed.stdout.strip().splitlines()[-1]))
    return steps, values


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Step-size convergence scan with Richardson orders")
    parser.add_argument("--input", default=None, help="input JSON with steps/values")
    parser.add_argument("--map", dest="map_command", default=None,
                        help="solver command reading h from stdin, writing Q(h) to stdout")
    parser.add_argument("--h0", type=float, default=0.1, help="initial step for --map mode")
    parser.add_argument("--levels", type=int, default=4, help="halving levels for --map mode")
    parser.add_argument("--tolerance", type=float, default=1e-3,
                        help="预登记收敛容差（--map 模式使用；--input 模式以 JSON 为准）")
    parser.add_argument("--output", required=True, help="output report JSON (must not exist)")
    args = parser.parse_args(argv)

    if args.input:
        input_path = Path(args.input)
        if not input_path.is_file():
            _fail(f"input not found: {input_path}")
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        steps = payload.get("steps")
        values = payload.get("values")
        if not isinstance(steps, list) or not isinstance(values, list) or not steps:
            _fail("input requires non-empty 'steps' and 'values' lists")
        if len(steps) != len(values) or len(steps) < 3:
            _fail("steps/values must be equal-length lists with at least 3 levels")
        steps = [float(item) for item in steps]
        values = [float(item) for item in values]
        tolerance = float(payload.get("tolerance", 1e-3))
        expected_order = payload.get("expected_order")
    elif args.map_command:
        steps, values = scan_with_map(args.map_command, args.h0, max(3, args.levels))
        tolerance = args.tolerance
        expected_order = None
    else:
        _fail("provide either --input JSON or --map solver command")

    diffs, orders = richardson_orders(steps, values)
    final_gap = diffs[-1] if diffs else abs(values[-1] - values[0])
    converged = final_gap <= tolerance
    observed_order = orders[-1] if orders else None
    order_ok = (
        True
        if expected_order is None or observed_order is None
        else observed_order >= 0.5 * float(expected_order)
    )
    status = "PASS" if converged and order_ok else "FAIL"
    report = {
        "schema": "mmflow-convergence-scan-report/v1",
        "steps": steps,
        "values": values,
        "successive_diffs": diffs,
        "richardson_orders": orders,
        "observed_order": observed_order,
        "expected_order": expected_order,
        "tolerance": tolerance,
        "final_gap": final_gap,
        "converged": converged,
        "order_ok": order_ok,
        "status": status,
    }
    output = Path(args.output)
    if output.exists():
        _fail(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "observed_order": observed_order,
                      "final_gap": final_gap, "output": str(output)},
                     ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
