from __future__ import annotations
from .plotting_common import save_figure, _series


def _draw(fig, data):
    import numpy as np

    ax = fig.add_subplot(111)
    x, y = _series(data)
    xf = np.asarray([float(v) for v in x])
    arr = np.asarray(y)
    y_pred = data.get("y_pred")
    if isinstance(y_pred, list):
        if len(y_pred) != len(x):
            raise ValueError("y_pred must match x/y length")
        pred = np.asarray([float(v) for v in y_pred])
        method = data.get("pred_label", "declared prediction")
    else:
        # 无声明预测时以线性最小二乘为对照，并如实标注来源
        if len(x) > 1 and float(xf.std()) > 0:
            slope, intercept = np.polyfit(xf, arr, 1)
            pred = slope * xf + intercept
            method = "OLS reference fit"
        else:
            pred = np.full_like(arr, arr.mean())
            method = "mean reference"
    residual = arr - pred
    sigma = float(residual.std(ddof=1)) if len(residual) > 1 else 0.0
    ax.scatter(pred, residual, s=34, color="#0072B2", alpha=0.85,
               edgecolors="white", linewidths=0.5, zorder=3)
    ax.axhline(0.0, color="#555555", linewidth=1.0)
    if sigma > 0:
        for k in (-2, 2):
            ax.axhline(k * sigma, color="#D55E00", linewidth=1.0,
                       linestyle=":",
                       label=("±2σ band" if k == 2 else None))
    ax.set_title(f"Residual diagnosis (reference: {method})")
    ax.set_xlabel(data["units"].get("x", "x"))
    ax.set_ylabel(data["units"].get("residual", "residual"))
    if sigma > 0:
        ax.legend(frameon=False, fontsize=8)
    ax.annotate(
        f"n={len(arr)}  σ={sigma:.3g}\nmax|r|={float(np.max(np.abs(residual))):.3g}",
        xy=(0.01, 0.98), xycoords="axes fraction", ha="left", va="top",
        fontsize=7.5,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white",
              "edgecolor": "#CCCCCC", "alpha": 0.9},
    )


def generate(data, output_dir):
    return save_figure(data, output_dir, role="validation", drawer=_draw)
