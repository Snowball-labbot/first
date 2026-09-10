from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure

_PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#56B4E9", "#E69F00"]


def _draw(fig, data):
    import numpy as np

    groups = data.get("groups")
    samples = data.get("samples")
    ax = fig.add_subplot(111)
    if isinstance(groups, dict) and groups:
        # 分组形态：箱线（分位/离群）叠加抖动散点（保留原始样本信息）
        names = [str(name) for name in groups]
        arrays = []
        for name in names:
            values = np.asarray(groups[name], dtype=float)
            if values.size == 0:
                raise ValueError(f"group {name!r} is empty")
            arrays.append(values)
        box = ax.boxplot(
            arrays, patch_artist=True, tick_labels=names, widths=0.55,
            medianprops={"color": "#D55E00", "linewidth": 1.6},
        )
        for patch, color in zip(box["boxes"], _PALETTE):
            patch.set_facecolor(color)
            patch.set_alpha(0.55)
            patch.set_edgecolor("#444444")
        rng = np.random.default_rng(2026)
        for i, values in enumerate(arrays, start=1):
            jitter = rng.uniform(-0.12, 0.12, size=values.size)
            ax.scatter(np.full(values.size, i) + jitter, values,
                       s=6, color="#333333", alpha=0.45, zorder=3)
        ax.set_ylabel(data["units"].get("y", "value"))
        ax.set_title("Grouped distribution (box + jittered samples)")
    elif isinstance(samples, list) and samples:
        # 单样本形态：直方图 + 经验累积分布（ECDF）双面板
        values = np.asarray(samples, dtype=float)
        if values.size == 0:
            raise ValueError("samples must be non-empty")
        ax.hist(values, bins=min(max(8, int(np.sqrt(values.size))), 40),
                color="#0072B2", alpha=0.7, edgecolor="white",
                density=True, label="histogram")
        ordered = np.sort(values)
        ecdf = np.arange(1, ordered.size + 1) / ordered.size
        ax2 = ax.twinx()
        ax2.plot(ordered, ecdf, color="#D55E00", linewidth=1.6,
                 drawstyle="steps-post", label="ECDF")
        ax2.set_ylim(0.0, 1.05)
        ax2.set_ylabel("empirical CDF", color="#D55E00")
        ax2.grid(False)
        ax.set_xlabel(data["units"].get("x", "value"))
        ax.set_ylabel(data["units"].get("y", "density"))
        ax.set_title("Distribution: histogram + ECDF")
        lines = [ax.get_legend_handle_labels(), ax2.get_legend_handle_labels()]
        ax.legend([item for pair in lines for item in pair[0]],
                  [item for pair in lines for item in pair[1]],
                  frameon=False, fontsize=8, loc="center right")
    else:
        raise ValueError(
            "distribution input requires 'groups' (name -> values) or 'samples'"
        )
    ax.tick_params(axis="x", rotation=20)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="distribution", drawer=_draw)
