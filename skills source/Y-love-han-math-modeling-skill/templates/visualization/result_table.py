from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure


def _draw(fig, data):
    columns = data.get("columns")
    rows = data.get("rows")
    if not isinstance(columns, list) or not columns:
        raise ValueError("result_table input requires a non-empty 'columns' list")
    if not isinstance(rows, list) or not rows or not all(
        isinstance(row, list) and len(row) == len(columns) for row in rows
    ):
        raise ValueError(
            "result_table input requires 'rows' as a list of lists matching 'columns' width"
        )
    ax = fig.add_subplot(111)
    ax.set_axis_off()
    cell_text = [[str(item) for item in row] for row in rows]
    highlight = data.get("highlight_column")
    col_idx = columns.index(highlight) if highlight in columns else None
    row_colors = None
    if col_idx is not None and rows:
        # 按高亮列数值排名着色：最优行淡绿、最差行淡红（方向由 highlight_direction 决定）
        direction = str(data.get("highlight_direction", "lower_is_better"))
        try:
            key_values = [float(row[col_idx]) for row in rows]
        except (TypeError, ValueError):
            key_values = None
        if key_values is not None:
            ordered = sorted(key_values, reverse=(direction == "lower_is_better"))
            rank = {value: index / max(len(ordered) - 1, 1) for index, value in enumerate(ordered)}
            row_colors = [
                ["#D8EFD3" if rank[float(row[col_idx])] == 0.0 else
                 ("#FBE3E1" if rank[float(row[col_idx])] == 1.0 else "#FFFFFF")
                 for _ in columns]
                for row in rows
            ]
    table = ax.table(
        cellText=cell_text,
        colLabels=[str(item) for item in columns],
        rowLabels=None,
        cellColours=row_colors,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.0, 1.45)
    for (row_index, col_index), cell in table.get_celld().items():
        if row_index == 0:
            cell.set_facecolor("#DCE7F2")
            cell.set_text_props(weight="bold")
        cell.set_edgecolor("#B9C4CE")
        if col_idx is not None and row_index > 0 and col_index == col_idx + 0:
            cell.set_linewidth(1.4)
    ax.set_title(data.get("title", "Results comparison"), pad=14)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="result_table", drawer=_draw)
