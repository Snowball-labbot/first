from __future__ import annotations
from .plotting_common import save_figure, _series


def _draw(fig, data):
    import numpy as np

    ax = fig.add_subplot(111)
    x, y = _series(data)
    arr = np.asarray(y)
    cleaned = data.get("y_clean")
    removed = data.get("removed_indices")
    if cleaned is not None:
        if not isinstance(cleaned, list) or len(cleaned) != len(x):
            raise ValueError("y_clean must match x length")
        clean_arr = np.asarray([float(v) for v in cleaned])
        ax.fill_between(x, arr, clean_arr, color="#CC79A7", alpha=0.18,
                        label="adjusted range")
        ax.plot(x, clean_arr, color="#009E73", marker="s", markersize=3.2,
                linewidth=1.6, label="after processing")
    else:
        # 未提供清洗序列时，给出滑动中位数作为处理效果参照（窗口=3/5）
        window = 3 if len(arr) < 20 else 5
        smooth = np.convolve(arr, np.ones(window) / window, mode="same")
        smooth[0] = arr[0]
        smooth[-1] = arr[-1]
        ax.plot(x, smooth, color="#009E73", linewidth=1.6,
                label=f"rolling median (w={window})")
    ax.plot(x, y, color="#0072B2", marker="o", markersize=3.4,
            linewidth=1.4, alpha=0.85, label="raw input")
    if isinstance(removed, list) and removed:
        idx = [i for i in removed if isinstance(i, int) and 0 <= i < len(x)]
        if idx:
            ax.scatter([x[i] for i in idx], [arr[i] for i in idx],
                       s=64, facecolors="none", edgecolors="#D55E00",
                       linewidths=1.4, zorder=4, label="removed points")
    ax.set_title("Preprocessing effect: raw vs processed")
    ax.set_xlabel(data["units"].get("x", "x"))
    ax.set_ylabel(data["units"].get("y", "y"))
    ax.legend(frameon=False, fontsize=8)
    delta = ""
    if cleaned is not None:
        shift = float(np.mean(np.abs(clean_arr - arr)))
        delta = f"\nmean|Δ|={shift:.3g}"
    ax.annotate(f"n={data['sample_size']}{delta}", xy=(0.99, 1.02),
                xycoords="axes fraction", ha="right", va="bottom",
                fontsize=8, color="#555555")


def generate(data, output_dir):
    return save_figure(data, output_dir, role="data_processing", drawer=_draw)
