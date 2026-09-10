from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure


def _draw(fig, data):
    import numpy as np

    matrix = data.get("matrix")
    if not isinstance(matrix, list) or not matrix or not all(
        isinstance(row, list) and row for row in matrix
    ):
        raise ValueError("heatmap input requires a non-empty 2D 'matrix' (list of rows)")
    values = np.asarray(matrix, dtype=float)
    ax = fig.add_subplot(111)
    image = ax.imshow(values, cmap="RdBu_r", aspect="auto")
    figure_colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
    figure_colorbar.set_label(data["units"].get("value", "value"))
    row_labels = data.get("row_labels")
    col_labels = data.get("col_labels")
    if isinstance(row_labels, list) and len(row_labels) == values.shape[0]:
        ax.set_yticks(range(values.shape[0]))
        ax.set_yticklabels([str(item) for item in row_labels], fontsize=8)
    if isinstance(col_labels, list) and len(col_labels) == values.shape[1]:
        ax.set_xticks(range(values.shape[1]))
        ax.set_xticklabels([str(item) for item in col_labels], fontsize=8,
                           rotation=35, ha="right")
    # 小矩阵直接标注数值，评委无需对照色标读数
    if values.shape[0] * values.shape[1] <= 225:
        threshold = float(np.abs(values).max()) / 2.0 if values.size else 0.0
        for i in range(values.shape[0]):
            for j in range(values.shape[1]):
                cell = values[i, j]
                ax.text(j, i, f"{cell:.3g}", ha="center", va="center",
                        fontsize=7.5,
                        color="white" if abs(cell) >= threshold else "#222222")
    ax.set_title(data.get("title", "Matrix heatmap (correlation / interaction)"))
    ax.grid(False)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="heatmap", drawer=_draw)
