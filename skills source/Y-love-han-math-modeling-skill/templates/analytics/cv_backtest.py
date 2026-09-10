# -*- coding: utf-8 -*-
"""
cv_backtest.py — 泄漏自检划分与回测评估（IID 预测适配器的划分实现）
用途：为 P4 冻结计划与 P6 时间回测提供三类免泄漏划分：
      kfold（IID 随机 K 折）、group_kfold（同组记录不跨集合）、
      expanding_window（按时间顺序扩张窗口）。每种划分都内置
      泄漏自检（训练/验证索引不相交、组不跨集合、时间不回看），
      输出可直接登记为 split 相关证据的划分摘要。
定位：骨架工具。评估函数由项目按题目补充；本脚本不做任何建模。

输入 JSON（--spec）字段：
{
  "mode": "kfold" | "group_kfold" | "expanding_window",
  "n_samples": 100,                       // kfold 必填
  "groups": ["g1", "g1", "g2", ...],      // group_kfold 必填，长度=样本数
  "n_samples_time": 100,                  // expanding_window 等价 n_samples
  "k": 5,                                  // kfold/group_kfold 折数（默认 5）
  "initial_train": 40,                     // expanding_window 初始训练窗
  "step": 10,                              // expanding_window 每步扩张量
  "horizon": 10                            // expanding_window 每步验证窗
}
运行方式：python cv_backtest.py --spec split_spec.json --output split_report.json
退出码：0 成功；2 输入不合法；3 泄漏自检失败
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy 为 analytics 层基线依赖
    np = None


def _fail(message: str) -> None:
    print(f"error: {message}")
    sys.exit(2)


def _stable_rng(seed_text: str):
    if np is None:
        _fail("cv_backtest requires numpy (analytics/requirements.txt)")
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16)
    return np.random.default_rng(seed)


def kfold_indices(n_samples: int, k: int, seed_text: str):
    rng = _stable_rng(seed_text)
    order = rng.permutation(n_samples)
    folds = [list(map(int, order[i::k])) for i in range(k)]
    splits = []
    for i in range(k):
        validation = sorted(folds[i])
        train = sorted(index for j in range(k) if j != i for index in folds[j])
        splits.append({"fold": i + 1, "train": train, "validation": validation})
    return splits


def group_kfold_indices(groups, k: int, seed_text: str):
    unique_groups = sorted(set(groups))
    if len(unique_groups) < k:
        _fail(f"group_kfold needs >= k distinct groups ({len(unique_groups)} < {k})")
    rng = _stable_rng(seed_text)
    shuffled = list(unique_groups)
    rng.shuffle(shuffled)
    assignment = {group: i % k for i, group in enumerate(shuffled)}
    folds = [[] for _ in range(k)]
    for index, group in enumerate(groups):
        folds[assignment[group]].append(index)
    splits = []
    for i in range(k):
        validation = sorted(folds[i])
        train = sorted(index for j in range(k) if j != i for index in folds[j])
        splits.append({"fold": i + 1, "train": train, "validation": validation})
    return splits


def expanding_window_indices(n_samples: int, initial_train: int, step: int, horizon: int):
    if initial_train + horizon > n_samples:
        _fail("expanding_window: initial_train + horizon exceeds n_samples")
    splits = []
    train_end = initial_train
    fold = 0
    while train_end + horizon <= n_samples:
        train = list(range(0, train_end))
        validation = list(range(train_end, train_end + horizon))
        splits.append({"fold": fold + 1, "train": train, "validation": validation})
        train_end += step
        fold += 1
    if not splits:
        _fail("expanding_window produced no splits")
    return splits


def leak_check(splits, mode: str, groups=None):
    """逐折断言：train/validation 不相交；group 模式下组不跨集合；
    expanding_window 模式下验证窗整体晚于训练窗。返回违规列表。"""
    violations = []
    for split in splits:
        train_set = set(split["train"])
        overlap = train_set & set(split["validation"])
        if overlap:
            violations.append({"fold": split["fold"], "kind": "index_overlap",
                               "detail": sorted(overlap)[:5]})
        if mode == "group_kfold" and groups is not None:
            train_groups = {groups[i] for i in split["train"]}
            validation_groups = {groups[i] for i in split["validation"]}
            shared = train_groups & validation_groups
            if shared:
                violations.append({"fold": split["fold"], "kind": "group_leakage",
                                   "detail": sorted(shared)[:5]})
        if mode == "expanding_window":
            if split["validation"] and split["train"]:
                if min(split["validation"]) < max(split["train"]) + 1:
                    violations.append({"fold": split["fold"],
                                       "kind": "temporal_backscan",
                                       "detail": "validation precedes training tail"})
    return violations


def evaluate_placeholder(splits):
    """评估占位：由项目按题目实现（返回结构化指标 dict 列表）。
    本骨架只统计样本量，避免把示例数字误当项目结果。"""
    return [
        {
            "fold": split["fold"],
            "train_size": len(split["train"]),
            "validation_size": len(split["validation"]),
            "metrics": "filled by project implementation",
        }
        for split in splits
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Leak-safe split and backtest harness")
    parser.add_argument("--spec", required=True, help="split specification JSON")
    parser.add_argument("--output", required=True, help="output report JSON (must not exist)")
    parser.add_argument("--seed-text", default="cv_backtest", help="stable shuffle seed text")
    args = parser.parse_args(argv)

    spec_path = Path(args.spec)
    if not spec_path.is_file():
        _fail(f"spec not found: {spec_path}")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    mode = spec.get("mode")
    k = int(spec.get("k", 5))
    if mode == "kfold":
        n = int(spec.get("n_samples", 0))
        if n < 2 * k:
            _fail("kfold needs n_samples >= 2k")
        splits = kfold_indices(n, k, args.seed_text)
        groups = None
    elif mode == "group_kfold":
        groups = spec.get("groups")
        if not isinstance(groups, list) or not groups:
            _fail("group_kfold requires a non-empty 'groups' list")
        splits = group_kfold_indices(groups, k, args.seed_text)
    elif mode == "expanding_window":
        n = int(spec.get("n_samples_time") or spec.get("n_samples") or 0)
        splits = expanding_window_indices(
            n, int(spec.get("initial_train", 0)),
            int(spec.get("step", 1)), int(spec.get("horizon", 1)),
        )
        groups = None
    else:
        _fail("mode must be one of kfold | group_kfold | expanding_window")

    violations = leak_check(splits, mode, groups if mode == "group_kfold" else None)
    report = {
        "schema": "mmflow-cv-backtest-report/v1",
        "mode": mode,
        "k": k,
        "splits": splits,
        "evaluation": evaluate_placeholder(splits),
        "leakage_violations": violations,
        "status": "FAIL" if violations else "PASS",
    }
    output = Path(args.output)
    if output.exists():
        _fail(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "splits": len(splits),
                      "violations": len(violations), "output": str(output)},
                     ensure_ascii=False))
    return 3 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
