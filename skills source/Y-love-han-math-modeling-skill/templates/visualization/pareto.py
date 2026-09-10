from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure


def _non_dominated_mask(points):
    import numpy as np

    values = np.asarray(points, dtype=float)
    count = values.shape[0]
    dominated = np.zeros(count, dtype=bool)
    for i in range(count):
        for j in range(count):
            if i == j:
                continue
            # 目标统一按"越小越好"归一（已由调用方折算）；j 支配 i 当且仅当
            # j 各维不劣且至少一维严格更优
            if np.all(values[j] <= values[i]) and np.any(values[j] < values[i]):
                dominated[i] = True
                break
    return dominated


def _draw(fig, data):
    import numpy as np

    points = data.get("points")
    if not isinstance(points, list) or not points or not all(
        isinstance(pair, (list, tuple)) and len(pair) == 2 for pair in points
    ):
        raise ValueError("pareto input requires 'points' as a list of [f1, f2] pairs")
    values = np.asarray(points, dtype=float)
    names = data.get("objective_names")
    if not isinstance(names, list) or len(names) != 2:
        names = ["objective 1", "objective 2"]
    # 目标方向：默认双目标最小化；声明 maximize 的维在比较前折算为最小化
    sense = data.get("sense", ["min", "min"])
    if not (isinstance(sense, list) and len(sense) == 2):
        raise ValueError("sense must be a pair like ['min', 'min']")
    comparable = np.array(
        [[item if sense[k] == "min" else -item for k, item in enumerate(pair)]
         for pair in points],
        dtype=float,
    )
    dominated = _non_dominated_mask(comparable)
    front = comparable[~dominated]
    order = np.argsort(front[:, 0])
    ax = fig.add_subplot(111)
    ax.scatter(values[dominated, 0], values[dominated, 1], s=22,
               color="#8C8C8C", alpha=0.6, label="dominated candidates")
    ax.plot(values[~dominated, 0][order], values[~dominated, 1][order],
            color="#D55E00", linewidth=1.5, alpha=0.85, zorder=2)
    ax.scatter(values[~dominated, 0], values[~dominated, 1], s=42,
               color="#0072B2", edgecolor="white", linewidth=0.8, zorder=3,
               label="Pareto front")
    ax.set_xlabel(data["units"].get("x", names[0]))
    ax.set_ylabel(data["units"].get("y", names[1]))
    ax.set_title("Bi-objective Pareto front (non-dominated set)")
    ax.legend(frameon=False, fontsize=8)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="pareto", drawer=_draw)
