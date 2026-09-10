from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure


def _draw(fig, data):
    from matplotlib.patches import FancyBboxPatch

    blocks = data.get("blocks")
    flows = data.get("flows")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("model_diagram input requires a non-empty 'blocks' list")
    if not isinstance(flows, list):
        raise ValueError("model_diagram input requires a 'flows' list")
    for block in blocks:
        if not isinstance(block, dict) or "id" not in block:
            raise ValueError("each block must be an object with an 'id'")
    known = {str(block["id"]) for block in blocks}
    for flow in flows:
        if not isinstance(flow, dict) or "source" not in flow or "target" not in flow:
            raise ValueError("each flow must be an object with 'source' and 'target'")
        if str(flow["source"]) not in known or str(flow["target"]) not in known:
            raise ValueError(f"flow references unknown block: {flow}")
    # 流水线布局：优先按 block 的显式 (x, y) 网格坐标；缺省时按"stage 行、
    # 行内序"自动排布——stage 值相同的块在同一水平行，行号由首次出现顺序决定
    coordinates = {}
    stage_rows = {}
    for block in blocks:
        block_id = str(block["id"])
        if "x" in block and "y" in block:
            coordinates[block_id] = (float(block["x"]), float(block["y"]))
        else:
            stage = str(block.get("stage", "1"))
            stage_rows.setdefault(stage, []).append(block)
    if not coordinates:
        row_gap = 1.0
        column_gap = 1.9
        for row_index, stage in enumerate(stage_rows):
            row_blocks = stage_rows[stage]
            for column_index, block in enumerate(row_blocks):
                coordinates[str(block["id"])] = (
                    column_index * column_gap,
                    -row_index * row_gap,
                )
    ax = fig.add_subplot(111)
    ax.set_axis_off()
    # 流（先画在下层）：支持 label 与 weight（线宽）
    weights = [float(flow["weight"]) for flow in flows if flow.get("weight") is not None]
    max_weight = max(weights) if weights else None
    for flow in flows:
        source = coordinates[str(flow["source"])]
        target = coordinates[str(flow["target"])]
        width = (
            1.0 + 2.6 * float(flow["weight"]) / max_weight
            if max_weight and max_weight > 0
            else 1.4
        )
        ax.annotate(
            "",
            xy=(target[0] - 0.32, target[1]),
            xytext=(source[0] + 0.32, source[1]),
            arrowprops={
                "arrowstyle": "-|>",
                "color": "#7A92A8",
                "linewidth": width,
                "shrinkA": 2,
                "shrinkB": 2,
            },
            zorder=1,
        )
        label = flow.get("label")
        if label:
            ax.annotate(
                str(label),
                ((source[0] + target[0]) / 2.0, (source[1] + target[1]) / 2.0 + 0.16),
                ha="center", fontsize=6.8, color="#4A5A6A", zorder=2,
            )
    # 块（画在上层）：统一圆角矩形 + 编号 + 标签
    for index, block in enumerate(blocks, start=1):
        block_id = str(block["id"])
        x, y = coordinates[block_id]
        label = str(block.get("label", block_id))
        box = FancyBboxPatch(
            (x - 0.3, y - 0.17), 0.6, 0.34,
            boxstyle="round,pad=0.045",
            facecolor="#DCE7F2" if block.get("emphasis") is not True else "#FBE3C8",
            edgecolor="#3F5B77", linewidth=1.1, zorder=3,
        )
        ax.add_patch(box)
        ax.text(x, y, f"{index}. {label}", ha="center", va="center",
                fontsize=7.6, zorder=4)
    xs = [item[0] for item in coordinates.values()]
    ys = [item[1] for item in coordinates.values()]
    ax.set_xlim(min(xs) - 0.75, max(xs) + 0.75)
    ax.set_ylim(min(ys) - 0.6, max(ys) + 0.6)
    ax.set_title(data.get("title", "Model pipeline"), pad=10)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="model_diagram", drawer=_draw)
