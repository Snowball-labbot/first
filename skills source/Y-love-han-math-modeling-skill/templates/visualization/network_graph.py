from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure

_PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#56B4E9", "#E69F00"]


def _layout(nodes, edges):
    """无坐标时的确定性布局：度数排序后的圆环布局（不引入 networkx 依赖）。"""
    import numpy as np

    ids = [str(node["id"]) for node in nodes]
    degree = {node_id: 0 for node_id in ids}
    for edge in edges:
        degree[str(edge["source"])] = degree.get(str(edge["source"]), 0) + 1
        degree[str(edge["target"])] = degree.get(str(edge["target"]), 0) + 1
    order = sorted(range(len(ids)), key=lambda i: (-degree[ids[i]], ids[i]))
    positions = {}
    count = len(ids)
    for rank, index in enumerate(order):
        angle = 2.0 * np.pi * rank / max(count, 1)
        positions[ids[index]] = (float(np.cos(angle)), float(np.sin(angle)))
    return positions


def _draw(fig, data):
    import numpy as np

    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("network_graph input requires a non-empty 'nodes' list")
    if not isinstance(edges, list):
        raise ValueError("network_graph input requires an 'edges' list")
    for node in nodes:
        if not isinstance(node, dict) or "id" not in node:
            raise ValueError("each node must be an object with an 'id'")
    for edge in edges:
        if not isinstance(edge, dict) or "source" not in edge or "target" not in edge:
            raise ValueError("each edge must be an object with 'source' and 'target'")
    ids = [str(node["id"]) for node in nodes]
    if len(set(ids)) != len(ids):
        raise ValueError("node ids must be unique")
    known = set(ids)
    for edge in edges:
        if str(edge["source"]) not in known or str(edge["target"]) not in known:
            raise ValueError(f"edge references unknown node: {edge}")
    provided = all("x" in node and "y" in node for node in nodes)
    positions = (
        {str(node["id"]): (float(node["x"]), float(node["y"])) for node in nodes}
        if provided
        else _layout(nodes, edges)
    )
    values = {str(node["id"]): node.get("value") for node in nodes}
    numeric = [float(values[key]) for key in ids if values[key] is not None]
    ax = fig.add_subplot(111)
    weights = [
        float(edge["weight"])
        for edge in edges
        if edge.get("weight") is not None
    ]
    max_weight = max(weights) if weights else None
    for edge in edges:
        source = positions[str(edge["source"])]
        target = positions[str(edge["target"])]
        weight = edge.get("weight")
        width = (
            0.6 + 3.4 * float(weight) / max_weight
            if max_weight and max_weight > 0 and weight is not None
            else 1.1
        )
        ax.plot([source[0], target[0]], [source[1], target[1]],
                color="#9DBBD8", linewidth=width, zorder=1, alpha=0.85)
    if numeric:
        lo, hi = min(numeric), max(numeric)
        span = (hi - lo) or 1.0
        sizes = {key: 40.0 + 320.0 * (float(values[key]) - lo) / span
                 if values[key] is not None else 60.0 for key in ids}
    else:
        sizes = {key: 70.0 for key in ids}
    for key in ids:
        x, y = positions[key]
        ax.scatter([x], [y], s=sizes[key], color="#0072B2",
                   edgecolor="white", linewidth=1.0, zorder=3)
        ax.annotate(str(key), (x, y), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=7.5, zorder=4)
    ax.set_axis_off()
    ax.set_title(data.get("title", "Network structure (node size = value)"))
    ax.relim()
    ax.autoscale_view()


def generate(data, output_dir):
    return save_figure(data, output_dir, role="network_graph", drawer=_draw)
