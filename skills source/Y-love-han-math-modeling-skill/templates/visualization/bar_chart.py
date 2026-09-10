from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure

_PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#56B4E9", "#E69F00"]


def _draw(fig, data):
    import numpy as np

    categories = data.get("categories")
    if not isinstance(categories, list) or not categories:
        raise ValueError("bar_chart input requires a non-empty 'categories' list")
    series = data.get("series")
    ax = fig.add_subplot(111)
    if isinstance(series, dict) and series:
        # 分组柱状图：多系列并列对比，可选误差棒
        names = [str(name) for name in series]
        arrays = []
        for name in names:
            values = series[name]
            if not isinstance(values, list) or len(values) != len(categories):
                raise ValueError(
                    f"series {name!r} must provide one value per category"
                )
            arrays.append([float(item) for item in values])
        errors = data.get("errors")
        if errors is not None:
            if not isinstance(errors, dict) or set(errors) != set(names):
                raise ValueError("'errors' keys must mirror 'series' keys")
            error_arrays = [
                [float(item) for item in errors[name]] for name in names
            ]
            if any(len(row) != len(categories) for row in error_arrays):
                raise ValueError("'errors' rows must match category count")
        else:
            error_arrays = None
        width = 0.8 / len(names)
        positions = np.arange(len(categories), dtype=float)
        for index, name in enumerate(names):
            offset = (index - (len(names) - 1) / 2.0) * width
            ax.bar(positions + offset, arrays[index], width=width * 0.92,
                   color=_PALETTE[index % len(_PALETTE)], label=name,
                   edgecolor="white", linewidth=0.5,
                   yerr=error_arrays[index] if error_arrays else None,
                   error_kw={"elinewidth": 1.0, "capsize": 2.5, "alpha": 0.8})
        ax.set_xticks(positions)
        ax.set_xticklabels([str(item) for item in categories], fontsize=8.5)
        ax.legend(frameon=False, fontsize=8, ncol=min(len(names), 3))
    else:
        # 单系列形态：values（可选 errors）
        values = data.get("values")
        if not isinstance(values, list) or len(values) != len(categories):
            raise ValueError("single-series form requires 'values' per category")
        bars = ax.bar([str(item) for item in categories],
                      [float(item) for item in values],
                      color="#0072B2", edgecolor="white", linewidth=0.5)
        errors = data.get("errors")
        if isinstance(errors, list) and len(errors) == len(values):
            ax.errorbar([str(item) for item in categories],
                        [float(item) for item in values],
                        yerr=[float(item) for item in errors],
                        fmt="none", ecolor="#333333", elinewidth=1.0,
                        capsize=2.5, alpha=0.8)
        # 值标注：单系列柱顶直接标数，便于论文引用精确数值
        for rect, value in zip(bars, values):
            alignment = "bottom" if value >= 0 else "top"
            ax.annotate(f"{float(value):.4g}",
                        (rect.get_x() + rect.get_width() / 2.0, value),
                        textcoords="offset points", xytext=(0, 3 if value >= 0 else -3),
                        ha="center", va=alignment, fontsize=7.5)
    ax.axhline(0.0, color="#555555", linewidth=0.8)
    ax.set_xlabel(data["units"].get("x", "category"))
    ax.set_ylabel(data["units"].get("y", "value"))
    ax.set_title(data.get("title", "Categorical comparison"))
    ax.tick_params(axis="x", rotation=20)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="bar_chart", drawer=_draw)
