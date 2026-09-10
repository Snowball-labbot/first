# -*- coding: utf-8 -*-
"""
evaluation_checks.py — 综合评价适配器检查（AHP/TOPSIS 判据实现）
用途：为 P6 评价类验证提供三项程序化判据：
      1) AHP 判断矩阵一致性比率 CR（CR < 0.1 通过）；
      2) TOPSIS 多档权重扰动的排名稳定性与反转检测；
      3) "宣称最优方案是否被支配"复核（非补偿解释缺口提示）。
依赖：numpy（analytics/requirements.txt）。
定位：检查工具。方案矩阵、权重与宣称结论由项目提供；本脚本只做判定，
      输出 validation_adapter_report / counterevidence_report 的检查素材。

输入 JSON（--input）字段：
{
  "ahp": {                              // 可选
      "matrix": [[1,3,5],[1/3,1,3],[1/5,1/3,1]]
  },
  "topsis": {                           // 可选
      "matrix": [[...方案x指标得分...]],
      "directions": ["max","min",...],  // 每列指标方向
      "weights": [0.5,0.3,0.2],
      "weight_perturbations": [0.05,0.1,0.2],  // 多档扰动幅度
      "claimed_best": 0                  // 宣称最优方案行号（可选）
  }
}
运行方式：python evaluation_checks.py --input eval.json --output eval_report.json
退出码：0 全部检查 PASS；1 存在 FAIL；2 输入不合法
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


def _fail(message: str) -> None:
    print(f"error: {message}")
    sys.exit(2)


# Saaty 随机一致性指标 RI（n=1..15，标准表值）
_RI = [0.0, 0.0, 0.58, 0.90, 1.12, 1.24, 1.32, 1.41, 1.45, 1.49, 1.51, 1.54,
       1.56, 1.57, 1.59]


def ahp_consistency(matrix):
    values = np.asarray(matrix, dtype=float)
    n = values.shape[0]
    if values.shape != (n, n) or n < 2:
        _fail("ahp.matrix must be a square matrix of size >= 2")
    eigenvalues, eigenvectors = np.linalg.eig(values)
    principal = int(np.argmax(eigenvalues.real))
    lambda_max = float(eigenvalues.real[principal])
    weights = np.abs(eigenvectors[:, principal].real)
    weights = weights / weights.sum()
    ci = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    ri = _RI[min(n, 15) - 1]
    cr = ci / ri if ri > 0 else 0.0
    return {
        "n": n, "lambda_max": lambda_max, "weights": weights.tolist(),
        "CI": ci, "RI": ri, "CR": cr,
        "CR_lt_01": cr < 0.1, "status": "PASS" if cr < 0.1 else "FAIL",
    }


def topsis(matrix, directions, weights):
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or values.shape[0] < 2:
        _fail("topsis.matrix must be a 2D matrix with >= 2 alternatives")
    if len(directions) != values.shape[1] or len(weights) != values.shape[1]:
        _fail("directions/weights length must match matrix columns")
    normalized = values / np.sqrt((values ** 2).sum(axis=0))
    weighted = normalized * np.asarray(weights, dtype=float)
    ideals, anti_ideals = [], []
    for column, direction in enumerate(directions):
        if direction == "max":
            ideals.append(weighted[:, column].max())
            anti_ideals.append(weighted[:, column].min())
        elif direction == "min":
            ideals.append(weighted[:, column].min())
            anti_ideals.append(weighted[:, column].max())
        else:
            _fail("directions entries must be 'max' or 'min'")
    ideal = np.asarray(ideals)
    anti = np.asarray(anti_ideals)
    d_plus = np.sqrt(((weighted - ideal) ** 2).sum(axis=1))
    d_minus = np.sqrt(((weighted - anti) ** 2).sum(axis=1))
    closeness = d_minus / (d_plus + d_minus)
    ranking = np.argsort(-closeness)
    return closeness, ranking


def topsis_stability(matrix, directions, weights, perturbations):
    """多档权重扰动：每档对每列权重施加 +/-delta（归一后重算 TOPSIS），
    记录最优方案是否变化（排名反转）。"""
    baseline_closeness, baseline_ranking = topsis(matrix, directions, weights)
    rows = [{
        "perturbation": 0.0, "direction": "baseline",
        "best": int(baseline_ranking[0]),
        "ranking": baseline_ranking.tolist(),
    }]
    reversals = []
    for delta in perturbations:
        for sign, tag in ((+1.0, "increase"), (-1.0, "decrease")):
            perturbed = np.asarray(weights, dtype=float) * (1.0 + sign * float(delta))
            if (perturbed <= 0).any():
                continue
            perturbed = perturbed / perturbed.sum()
            _, ranking = topsis(matrix, directions, perturbed.tolist())
            best = int(ranking[0])
            if best != int(baseline_ranking[0]):
                reversals.append({"perturbation": float(delta), "direction": tag,
                                  "best": best})
            rows.append({"perturbation": float(delta), "direction": tag,
                         "best": best, "ranking": ranking.tolist()})
    return {
        "baseline_best": int(baseline_ranking[0]),
        "baseline_ranking": baseline_ranking.tolist(),
        "baseline_closeness": baseline_closeness.tolist(),
        "runs": rows,
        "reversals": reversals,
        "status": "FAIL" if reversals else "PASS",
    }


def domination_check(matrix, directions, claimed_best):
    """宣称最优方案被支配复核：存在其他方案各维不劣且至少一维严格更优，
    即宣称需要非补偿解释支撑。"""
    values = np.asarray(matrix, dtype=float)
    if claimed_best is None:
        return {"status": "NOT_APPLICABLE", "note": "claimed_best not provided"}
    index = int(claimed_best)
    if not (0 <= index < values.shape[0]):
        _fail("claimed_best out of range")
    target = values[index]
    for other in range(values.shape[0]):
        if other == index:
            continue
        row = values[other]
        comparable = [
            row[k] <= target[k] if directions[k] == "min" else row[k] >= target[k]
            for k in range(values.shape[1])
        ]
        strictly = [
            row[k] < target[k] if directions[k] == "min" else row[k] > target[k]
            for k in range(values.shape[1])
        ]
        if all(comparable) and any(strictly):
            return {"status": "FAIL", "dominated_by": other,
                    "note": "claimed best is dominated; non-compensatory justification required"}
    return {"status": "PASS", "dominated_by": None}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AHP/TOPSIS adapter checks")
    parser.add_argument("--input", required=True, help="input JSON")
    parser.add_argument("--output", required=True, help="output report JSON (must not exist)")
    args = parser.parse_args(argv)
    if np is None:
        _fail("evaluation_checks requires numpy (analytics/requirements.txt)")

    input_path = Path(args.input)
    if not input_path.is_file():
        _fail(f"input not found: {input_path}")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    checks = {}

    ahp = payload.get("ahp")
    if isinstance(ahp, dict) and ahp.get("matrix"):
        checks["ahp_consistency"] = ahp_consistency(ahp["matrix"])

    topsis_spec = payload.get("topsis")
    if isinstance(topsis_spec, dict) and topsis_spec.get("matrix"):
        directions = topsis_spec.get("directions")
        weights = topsis_spec.get("weights")
        if not isinstance(directions, list) or not isinstance(weights, list):
            _fail("topsis requires 'directions' and 'weights' lists")
        perturbations = topsis_spec.get("weight_perturbations", [0.05, 0.1, 0.2])
        checks["topsis_stability"] = topsis_stability(
            topsis_spec["matrix"], directions, weights, perturbations
        )
        checks["domination_check"] = domination_check(
            topsis_spec["matrix"], directions, topsis_spec.get("claimed_best")
        )

    if not checks:
        _fail("input must provide 'ahp' and/or 'topsis' sections")
    overall = "FAIL" if any(item.get("status") == "FAIL" for item in checks.values()) else "PASS"
    report = {"schema": "mmflow-evaluation-checks-report/v1",
              "checks": checks, "status": overall}
    output = Path(args.output)
    if output.exists():
        _fail(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": overall,
                      "checks": list(checks), "output": str(output)},
                     ensure_ascii=False))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
