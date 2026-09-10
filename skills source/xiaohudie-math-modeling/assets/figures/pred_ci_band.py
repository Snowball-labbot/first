# -*- coding: utf-8 -*-
"""高级绘图模板：预测结果 + 95% 置信带（预测类必备核心图）。

基于 common.py 规范：无图内标题、300DPI、去上右边框、置信带 fill_between。
运行自测：python pred_ci_band.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from common import COLORS, FIG_SINGLE, despine, save_fig  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def plot_pred_with_ci(t_train, y_train, t_test, y_pred, ci_lower, ci_upper,
                      y_test=None, xlabel="时间", ylabel="数值", name_cn="预测结果与置信区间"):
    """绘制历史观测、预测曲线与 95% 置信带，并标注区间覆盖率。"""
    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    ax.plot(t_train, y_train, "-o", color=COLORS["neutral"], lw=1.5, ms=3, label="历史观测")
    ax.plot(t_test, y_pred, "-s", color=COLORS["primary"], lw=1.5, ms=4, label="预测值")
    ax.fill_between(t_test, ci_lower, ci_upper, color=COLORS["light"], alpha=0.45,
                    label="95% 置信区间")
    if y_test is not None:
        ax.plot(t_test, y_test, "^", color=COLORS["accent"], ms=5, label="真实值")
        cover = float(np.mean((np.asarray(y_test) >= ci_lower) & (np.asarray(y_test) <= ci_upper)))
        ax.annotate(f"区间覆盖率 {cover:.0%}", xy=(0.03, 0.92), xycoords="axes fraction")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.3, linestyle="--")
    ax.legend(frameon=False, loc="best")
    despine(ax)
    path = save_fig(fig, name_cn)
    # 数据特征输出（论文描述必须基于此，禁止看图猜）
    print(f"【{name_cn} 数据特征】预测起点={y_pred[0]:.2f}，终点={y_pred[-1]:.2f}，"
          f"趋势={'上升' if y_pred[-1] > y_pred[0] else '下降'}")
    return path


if __name__ == "__main__":
    rng = np.random.default_rng(2)
    t_train = np.arange(0, 24)
    y_train = 50 + 1.1 * t_train + 6 * np.sin(2 * np.pi * t_train / 12) + rng.normal(0, 2, 24)
    t_test = np.arange(24, 32)
    true = 50 + 1.1 * t_test + 6 * np.sin(2 * np.pi * t_test / 12)
    y_pred = true + rng.normal(0, 1.2, 8)
    half = 2.8 + 0.15 * np.arange(8)
    plot_pred_with_ci(t_train, y_train, t_test, y_pred, y_pred - half, y_pred + half, y_test=true)
    print("pred_ci_band.py 自测通过")
