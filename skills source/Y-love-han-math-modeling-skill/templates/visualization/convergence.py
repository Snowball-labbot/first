from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure


def _draw(fig, data):
    import numpy as np

    x, y = None, None
    if isinstance(data.get("h"), list) and isinstance(data.get("error"), list):
        x = [float(item) for item in data["h"]]
        y = [float(item) for item in data["error"]]
    elif isinstance(data.get("refinement"), list):
        pairs = data["refinement"]
        if not all(isinstance(pair, (list, tuple)) and len(pair) == 2 for pair in pairs):
            raise ValueError("refinement items must be [step, error] pairs")
        x = [float(pair[0]) for pair in pairs]
        y = [float(pair[1]) for pair in pairs]
    if not x or len(x) != len(y) or len(x) < 2:
        raise ValueError(
            "convergence input requires 'h' + 'error' (or 'refinement' pairs), length >= 2"
        )
    steps = np.asarray(x)
    errors = np.asarray(y)
    if np.any(steps <= 0) or np.any(errors <= 0):
        raise ValueError("steps and errors must be positive for log-log convergence")
    order = np.argsort(steps)
    steps = steps[order]
    errors = errors[order]
    slope, intercept = np.polyfit(np.log(steps), np.log(errors), 1)
    observed_order = -slope
    ax = fig.add_subplot(111)
    ax.loglog(steps, errors, "o", color="#0072B2", markersize=5,
              label="measured error")
    fit = np.exp(intercept) * steps ** slope
    ax.loglog(steps, fit, "--", color="#D55E00", linewidth=1.4,
              label=f"fit: error ~ h^{observed_order:.2f}")
    # 参考 O(h) 与 O(h^2) 斜率三角形，读图者可直接判断收敛阶是否达标
    reference = float(data.get("reference_order", 2.0))
    anchor = errors[-1]
    ax.loglog([steps[-1], steps[0]], [anchor, anchor * (steps[-1] / steps[0]) ** (-reference)],
              ":", color="#009E73", linewidth=1.2,
              label=f"O(h^{reference:g}) reference")
    ax.set_xlabel(data["units"].get("x", "step size h"))
    ax.set_ylabel(data["units"].get("y", "error"))
    ax.set_title(f"Grid convergence (observed order p = {observed_order:.2f})")
    ax.legend(frameon=False, fontsize=8, loc="best")
    note = data.get("conclusion_note")
    if isinstance(note, str) and note:
        ax.annotate(note, xy=(0.02, 0.02), xycoords="axes fraction",
                    fontsize=7.5, color="#333333", ha="left", va="bottom")


def generate(data, output_dir):
    return save_figure(data, output_dir, role="convergence", drawer=_draw)
