from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure


def _draw(fig, data):
    import numpy as np

    x = data.get("x")
    y = data.get("y")
    if not isinstance(x, list) or not isinstance(y, list) or not x or len(x) != len(y):
        raise ValueError("scatter_fit input requires equal non-empty 'x' and 'y' lists")
    xs = np.asarray([float(item) for item in x])
    ys = np.asarray([float(item) for item in y])
    ax = fig.add_subplot(111)
    ax.scatter(xs, ys, s=24, color="#0072B2", alpha=0.8,
               edgecolor="white", linewidth=0.5, label="observed")
    # 拟合线：显式 slope/intercept，或 fit_y 序列；缺省时用最小二乘
    fit_mode = data.get("fit")
    if isinstance(fit_mode, dict) and ("slope" in fit_mode or "intercept" in fit_mode):
        slope = float(fit_mode.get("slope", 0.0))
        intercept = float(fit_mode.get("intercept", 0.0))
        fit_label = str(fit_mode.get("label", f"fit: y = {slope:.3g}x + {intercept:.3g}"))
        fit_y = slope * xs + intercept
    elif isinstance(data.get("fit_y"), list):
        if len(data["fit_y"]) != len(x):
            raise ValueError("'fit_y' must match 'x' length")
        fit_y = np.asarray([float(item) for item in data["fit_y"]])
        fit_label = str(data.get("fit_label", "model fit"))
    elif isinstance(fit_mode, dict) and fit_mode.get("least_squares") is True:
        slope, intercept = np.polyfit(xs, ys, 1)
        fit_y = slope * xs + intercept
        fit_label = f"least squares: y = {slope:.3g}x + {intercept:.3g}"
    else:
        fit_y = None
        fit_label = None
    if fit_y is not None:
        order = np.argsort(xs)
        ax.plot(xs[order], fit_y[order], color="#D55E00", linewidth=1.7,
                label=fit_label)
    # 基线对照（如基线模型预测），与 y=x 参照（观测=预测恒等线）
    if isinstance(data.get("baseline_y"), list):
        if len(data["baseline_y"]) != len(x):
            raise ValueError("'baseline_y' must match 'x' length")
        baseline = np.asarray([float(item) for item in data["baseline_y"]])
        order = np.argsort(xs)
        ax.plot(xs[order], baseline[order], ":", color="#009E73", linewidth=1.4,
                label=str(data.get("baseline_label", "baseline")))
    if data.get("show_identity", False):
        lo = float(min(xs.min(), ys.min()))
        hi = float(max(xs.max(), ys.max()))
        ax.plot([lo, hi], [lo, hi], "--", color="#888888", linewidth=1.0,
                label="y = x reference")
    ax.set_xlabel(data["units"].get("x", "x"))
    ax.set_ylabel(data["units"].get("y", "y"))
    ax.set_title(data.get("title", "Scatter with fit and references"))
    ax.legend(frameon=False, fontsize=8, loc="best")


def generate(data, output_dir):
    return save_figure(data, output_dir, role="scatter_fit", drawer=_draw)
