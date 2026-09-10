from __future__ import annotations
from .plotting_common import save_figure


def _layered_layout(nodes, edges):
    """无显式坐标时的分层 DAG 自动布局。

    按有向边的最长路径给节点分层（源点在第 0 层），层内等距水平排布。
    旧版把所有节点排在 y=0 一条水平线上，箭头全部重叠，技术路线图
    不可用；此布局保证层级自上而下、同层互不遮挡。显式提供 x/y 的
    节点仍以手工坐标优先。含环时回退为按出现顺序分层并标注警告字段。
    """
    ids = [node["id"] for node in nodes]
    id_set = set(ids)
    succs = {i: [] for i in ids}
    for edge in edges:
        s, t = edge.get("source"), edge.get("target")
        if s in id_set and t in id_set and s != t:
            succs[s].append(t)

    def longest_depth():
        # 迭代松弛求最长路径分层；len(ids)+1 轮仍在变化即存在环。
        depth = {i: 0 for i in ids}
        for _round in range(len(ids) + 1):
            changed = False
            for n in ids:
                for m in succs[n]:
                    if depth[m] < depth[n] + 1:
                        depth[m] = depth[n] + 1
                        changed = True
            if not changed:
                return depth, False
        return depth, True

    depth, cyclic = longest_depth()
    layers = {}
    for n in ids:
        layers.setdefault(depth[n], []).append(n)
    positions = {}
    max_layer = max(layers) if layers else 0
    for layer, members in sorted(layers.items()):
        width = len(members)
        for k, n in enumerate(sorted(members)):
            x = (k + 1) / (width + 1)
            y = 1.0 - layer / (max_layer + 1) if max_layer else 0.5
            positions[n] = (x, y)
    for node in nodes:
        if node.get("x") is not None and node.get("y") is not None:
            positions[node["id"]] = (node["x"], node["y"])
    return positions, cyclic


def _draw(fig, data):
    ax = fig.add_subplot(111)
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    if not nodes:
        raise ValueError("architecture figure requires real nodes")
    positions, cyclic = _layered_layout(nodes, edges)
    for edge in edges:
        if edge["source"] in positions and edge["target"] in positions:
            x1, y1 = positions[edge["source"]]
            x2, y2 = positions[edge["target"]]
            ax.annotate(
                "", xy=(x2, y2), xytext=(x1, y1),
                arrowprops={"arrowstyle": "->", "color": "#777777",
                            "shrinkA": 14, "shrinkB": 14},
            )
    palette = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#56B4E9"]
    for i, node in enumerate(nodes):
        x, y = positions[node["id"]]
        color = node.get("color", palette[i % len(palette)])
        ax.scatter([x], [y], s=900, color=color, alpha=.88, zorder=3,
                   edgecolors="white", linewidths=1.5)
        ax.text(x, y, node.get("label", node["id"]), ha="center", va="center",
                color="white", fontsize=8.5, zorder=4)
    title = "Evidence and modeling architecture"
    if cyclic:
        title += " (cycle detected: layout approximated)"
    ax.set_title(title)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.08, 1.08)
    ax.axis("off")


def generate(data, output_dir):
    return save_figure(data, output_dir, role="architecture", drawer=_draw)
