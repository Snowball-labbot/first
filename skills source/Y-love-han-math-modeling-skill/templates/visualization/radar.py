from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure

_PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#56B4E9"]


def _draw(fig, data):
    import numpy as np

    indicators = data.get("indicators")
    series = data.get("series")
    if not isinstance(indicators, list) or len(indicators) < 3:
        raise ValueError("radar input requires at least 3 'indicators'")
    if not isinstance(series, dict) or not series:
        raise ValueError("radar input requires 'series' (name -> normalized scores)")
    count = len(indicators)
    for name, values in series.items():
        if not isinstance(values, list) or len(values) != count:
            raise ValueError(f"series {name!r} must have one score per indicator")
    angles = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False).tolist()
    angles += angles[:1]
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_offset(np.pi / 2.0)
    ax.set_theta_direction(-1.0)
    for i, (name, values) in enumerate(series.items()):
        scores = [float(item) for item in values]
        closed = scores + scores[:1]
        color = _PALETTE[i % len(_PALETTE)]
        ax.plot(angles, closed, color=color, linewidth=1.7, label=str(name))
        ax.fill(angles, closed, color=color, alpha=0.12)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([str(item) for item in indicators], fontsize=8.5)
    # 归一化分数默认落在 [0, 1]；给出参考环而不是主观满分线
    ax.set_ylim(0.0, float(data.get("score_max", 1.0)))
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=7, color="#666666")
    ax.set_title("Composite evaluation radar", pad=18)
    ax.legend(frameon=False, fontsize=8, loc="upper right",
              bbox_to_anchor=(1.28, 1.08))
    ax.grid(alpha=0.35)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="radar", drawer=_draw)
