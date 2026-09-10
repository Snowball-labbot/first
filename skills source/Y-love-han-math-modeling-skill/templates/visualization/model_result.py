from __future__ import annotations
from .plotting_common import save_figure, _series


def _draw(fig, data):
    import numpy as np

    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1.15], hspace=0.12)
    ax = fig.add_subplot(gs[0])
    x, y = _series(data)
    arr = np.asarray(y)
    lower = data.get("lower")
    upper = data.get("upper")
    if isinstance(lower, list) and isinstance(upper, list) \
            and len(lower) == len(x) and len(upper) == len(x):
        ax.fill_between(x, lower, upper, color="#0072B2", alpha=0.16,
                        label="uncertainty band")
    ax.plot(x, y, color="#0072B2", marker="o", markersize=3.4,
            linewidth=1.8, label="model result")
    baseline = data.get("y_baseline")
    if isinstance(baseline, list):
        if len(baseline) != len(x):
            raise ValueError("y_baseline must match x length")
        ax.plot(x, baseline, color="#999999", linewidth=1.3,
                linestyle="--", label="baseline")
    ax.set_title("Model result with uncertainty and residual diagnosis")
    ax.set_xlabel(data["units"].get("x", "x"))
    ax.set_ylabel(data["units"].get("y", "y"))
    ax.legend(frameon=False, fontsize=8, loc="upper left")

    # 残差面板：有拟合参照时画真实残差；否则画对均值/趋势线的偏差并如实标注
    res_ax = fig.add_subplot(gs[1], sharex=ax)
    if isinstance(baseline, list):
        residual = arr - np.asarray([float(v) for v in baseline])
        ref_label = "residual vs baseline"
    else:
        xf = np.asarray([float(v) for v in x])
        if len(x) > 1 and float(xf.std()) > 0:
            slope, intercept = np.polyfit(xf, arr, 1)
            residual = arr - (slope * xf + intercept)
            ref_label = "residual vs linear trend"
        else:
            residual = arr - arr.mean()
            ref_label = "deviation from mean"
    res_ax.axhline(0.0, color="#888888", linewidth=0.9)
    res_ax.bar(range(len(residual)), residual,
               color=["#D55E00" if v < 0 else "#0072B2" for v in residual],
               alpha=0.8, width=0.8)
    std = float(residual.std(ddof=1)) if len(residual) > 1 else 0.0
    if std > 0:
        for k in (-2, 2):
            res_ax.axhline(k * std, color="#CC79A7", linewidth=0.9,
                           linestyle=":", label=("±2σ" if k == 2 else None))
    res_ax.set_ylabel(ref_label, fontsize=8)
    res_ax.tick_params(labelsize=7.5)
    handles, labels = res_ax.get_legend_handles_labels()
    if handles:
        res_ax.legend(frameon=False, fontsize=7)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="model_result", drawer=_draw)
