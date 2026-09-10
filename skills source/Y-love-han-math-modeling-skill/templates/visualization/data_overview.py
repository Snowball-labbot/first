from __future__ import annotations
from .plotting_common import save_figure, _series


def _draw(fig, data):
    import numpy as np

    ax = fig.add_subplot(111)
    x, y = _series(data)
    arr = np.asarray(y)
    mean = float(arr.mean())
    std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    if len(arr) > 1:
        ax.fill_between(x, mean - std, mean + std,
                        color="#0072B2", alpha=0.12, label="mean±std")
    ax.axhline(mean, color="#D55E00", linewidth=1.2, linestyle="--",
               label=f"mean={mean:.3g}")
    # 可选多序列叠加：series: {name: [y...]}，长度须与 x 一致
    extra = data.get("series")
    if isinstance(extra, dict):
        for i, (name, vals) in enumerate(extra.items()):
            if not isinstance(vals, list) or len(vals) != len(x):
                raise ValueError(
                    f"series {name!r} must match x length"
                )
            ax.plot(x, vals, linewidth=1.3, alpha=0.9,
                    color=["#009E73", "#CC79A7", "#56B4E9"][i % 3],
                    label=str(name))
    ax.plot(x, y, color="#0072B2", marker="o", markersize=3.4,
            linewidth=1.8, label="observed")
    ax.set_title("Data overview: level, dispersion and composition")
    ax.set_xlabel(data["units"].get("x", "x"))
    ax.set_ylabel(data["units"].get("y", "y"))
    # 统计摘要框：一图承载位置/离散/极值三重信息
    q1 = float(np.percentile(arr, 25)) if len(arr) >= 4 else float(arr.min())
    q3 = float(np.percentile(arr, 75)) if len(arr) >= 4 else float(arr.max())
    stats_text = (
        f"n={len(arr)}\nmean={mean:.3g}\nstd={std:.3g}\n"
        f"min={arr.min():.3g}  max={arr.max():.3g}\nIQR=[{q1:.3g},{q3:.3g}]"
    )
    ax.annotate(stats_text, xy=(0.01, 0.98), xycoords="axes fraction",
                ha="left", va="top", fontsize=7.5,
                bbox={"boxstyle": "round,pad=0.35", "facecolor": "white",
                      "edgecolor": "#CCCCCC", "alpha": 0.9})
    ax.legend(frameon=False, fontsize=8, loc="lower right")


def generate(data, output_dir):
    return save_figure(data, output_dir, role="data_overview", drawer=_draw)
