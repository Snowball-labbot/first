# -*- coding: utf-8 -*-
"""高级绘图模板：雷达图（评价类多方案多维对比）。

纯 matplotlib 实现（评价类综合得分的直观展示）；方案 ≤6 个、维度 ≤8 个效果最好。
运行自测：python radar_chart.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from common import DEFAULT_COLORS, FIG_SQUARE, save_fig  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def plot_radar(labels, series, name_cn="多方案雷达图", maximize_only=True):
    """雷达图。

    labels: 维度名列表；series: {方案名: 各维度得分(已同向化到 [0,1])}。
    maximize_only=True 时假设所有维度已正向化（负向指标先取倒数/反向标准化）。
    """
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=FIG_SQUARE, subplot_kw=dict(polar=True))
    for i, (name, vals) in enumerate(series.items()):
        v = list(map(float, vals)) + [float(vals[0])]
        ax.plot(angles, v, color=DEFAULT_COLORS[i % len(DEFAULT_COLORS)],
                lw=1.6, label=name, marker="o", ms=3)
        ax.fill(angles, v, color=DEFAULT_COLORS[i % len(DEFAULT_COLORS)], alpha=0.10)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.3, linestyle="--")
    ax.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.25, 1.05))
    path = save_fig(fig, name_cn)
    # 数据特征输出
    for name, vals in series.items():
        print(f"【{name_cn} 数据特征】{name}：均值={np.mean(vals):.3f}，"
              f"最强维度={labels[int(np.argmax(vals))]}，最弱维度={labels[int(np.argmin(vals))]}")
    return path


if __name__ == "__main__":
    labels = ["经济", "环境", "社会", "创新", "效率", "稳定"]
    series = {
        "方案A": [0.82, 0.55, 0.71, 0.64, 0.78, 0.69],
        "方案B": [0.70, 0.81, 0.62, 0.75, 0.60, 0.83],
        "方案C": [0.60, 0.66, 0.80, 0.55, 0.72, 0.58],
    }
    plot_radar(labels, series)
    print("radar_chart.py 自测通过")
