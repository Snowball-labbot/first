# -*- coding: utf-8 -*-
"""高级绘图模板：相关性热力图（matplotlib imshow 实现，替代 sns.heatmap）。

Diverging 配色 RdBu_r、标注 r 值、支持掩码上三角（更清爽）。
运行自测：python corr_heatmap.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from common import FIG_SQUARE, save_fig  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def plot_corr_heatmap(df, name_cn="相关性热力图", mask_upper=True, figsize=None):
    """变量相关性热力图。

    df: 数值型 DataFrame。mask_upper=True 只显示下三角。
    返回（图路径, 相关系数矩阵）。同时打印最强正/负相关对。
    """
    corr = df.corr(numeric_only=True).values
    cols = list(df.select_dtypes("number").columns)
    n = len(cols)
    if mask_upper:
        show = corr.copy()
        iu = np.triu_indices(n, k=1)
        show[iu] = np.nan
    else:
        show = corr

    fig, ax = plt.subplots(figsize=figsize or FIG_SQUARE)
    im = ax.imshow(show, cmap="RdBu_r", vmin=-1, vmax=1)
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_xticks(range(n), cols, rotation=45, ha="right")
    ax.set_yticks(range(n), cols)
    for i in range(n):
        for j in range(n):
            if not np.isnan(show[i, j]):
                ax.text(j, i, f"{show[i, j]:.2f}", ha="center", va="center",
                        fontsize=8,
                        color="white" if abs(corr[i, j]) > 0.6 else "black")
    ax.spines[:].set_visible(False)
    path = save_fig(fig, name_cn)

    # 数据特征输出（论文引用）
    tri = corr[np.tril_indices(n, k=-1)]
    pairs = [(cols[i], cols[j], corr[i, j])
             for i in range(n) for j in range(n) if i > j]
    strongest_pos = max(pairs, key=lambda p: p[2])
    strongest_neg = min(pairs, key=lambda p: p[2])
    print(f"【{name_cn} 数据特征】最强正相关：{strongest_pos[0]} vs {strongest_pos[1]} "
          f"(r={strongest_pos[2]:.3f})；最强负相关：{strongest_neg[0]} vs {strongest_neg[1]} "
          f"(r={strongest_neg[2]:.3f})；|r|>0.7 的指标对 {sum(abs(tri) > 0.7)} 对")
    return path, corr


if __name__ == "__main__":
    import pandas as pd
    rng = np.random.default_rng(9)
    base = rng.normal(0, 1, 200)
    df = pd.DataFrame({
        "产量": 100 + 8 * base + rng.normal(0, 3, 200),
        "投入": 40 + 5 * base + rng.normal(0, 4, 200),          # 与产量强相关
        "气温": rng.uniform(10, 35, 200),
        "利润": 20 + 3 * base - 0.5 * rng.uniform(10, 35, 200) + rng.normal(0, 2, 200),
    })
    plot_corr_heatmap(df)
    print("corr_heatmap.py 自测通过")
