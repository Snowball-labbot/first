# -*- coding: utf-8 -*-
"""高级绘图模板：ROC 曲线 + Bootstrap 置信带（分类/风险评估）。

sklearn 生成 ROC 与 AUC，Bootstrap 估计置信带；AUC 含误差棒式标注。
运行自测：python roc_with_ci.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from common import COLORS, FIG_SINGLE, despine, save_fig  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def plot_roc_with_ci(y_true, y_score, n_boot=300, seed=42, name_cn="ROC曲线"):
    """ROC 曲线 + Bootstrap 95% 置信带 + AUC 标注。"""
    from sklearn.metrics import auc, roc_curve

    rng = np.random.default_rng(seed)
    fpr, tpr, _ = roc_curve(y_true, y_score)
    auc_val = auc(fpr, tpr)

    # Bootstrap 置信带（重采样样本，等宽 FPR 网格插值）
    grid = np.linspace(0, 1, 101)
    boots = []
    y_true, y_score = np.asarray(y_true), np.asarray(y_score)
    n = len(y_true)
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(np.unique(y_true[idx])) < 2:
            continue
        f, t, _ = roc_curve(y_true[idx], y_score[idx])
        boots.append(np.interp(grid, f, t))
    boots = np.asarray(boots)
    lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)

    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    ax.fill_between(grid, lo, hi, color=COLORS["light"], alpha=0.5, label="Bootstrap 95% 置信带")
    ax.plot(fpr, tpr, color=COLORS["primary"], lw=1.8, label=f"ROC (AUC={auc_val:.3f})")
    ax.plot([0, 1], [0, 1], "--", color=COLORS["neutral"], lw=1, label="随机基准 (AUC=0.5)")
    ax.set_xlabel("假正率 FPR")
    ax.set_ylabel("真正率 TPR")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3, linestyle="--")
    ax.legend(frameon=False, loc="lower right")
    despine(ax)
    path = save_fig(fig, name_cn)
    print(f"【{name_cn} 数据特征】AUC={auc_val:.4f}；95% 置信带宽度中位数={np.median(hi - lo):.3f}"
          f"（越窄越稳定）；Bootstrap 有效次数={len(boots)}")
    return path, auc_val


if __name__ == "__main__":
    from sklearn.datasets import make_classification
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split

    X, y = make_classification(n_samples=500, n_features=8, n_informative=5,
                               weights=[0.6, 0.4], random_state=7)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=7, stratify=y)
    clf = RandomForestClassifier(n_estimators=200, random_state=7).fit(Xtr, ytr)
    score = clf.predict_proba(Xte)[:, 1]
    _, auc_val = plot_roc_with_ci(yte, score)
    assert auc_val > 0.7, "信息量充分的合成数据 AUC 应较高"
    print("roc_with_ci.py 自测通过")
