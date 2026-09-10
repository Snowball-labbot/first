from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure


def _draw(fig, data):
    import numpy as np

    points = data.get("points")
    grid = data.get("grid")
    ax = fig.add_subplot(111)
    if isinstance(grid, dict) and isinstance(grid.get("values"), list):
        # 栅格形态：values 二维矩阵 + 线性地理坐标（x0,y0,dx,dy）或 extent
        values = np.asarray(grid["values"], dtype=float)
        if values.ndim != 2 or values.size == 0:
            raise ValueError("grid.values must be a non-empty 2D matrix")
        extent = grid.get("extent")
        if isinstance(extent, list) and len(extent) == 4:
            extent_args = [float(item) for item in extent]
        else:
            x0 = float(grid.get("x0", 0.0))
            y0 = float(grid.get("y0", 0.0))
            dx = float(grid.get("dx", 1.0))
            dy = float(grid.get("dy", 1.0))
            extent_args = [x0, x0 + dx * values.shape[1],
                           y0, y0 + dy * values.shape[0]]
        image = ax.imshow(values, origin="lower", extent=extent_args,
                          cmap="viridis", aspect="equal")
        figure_colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
        figure_colorbar.set_label(data["units"].get("value", "value"))
    elif isinstance(points, list) and points:
        # 点位形态：[{x, y, value?, label?}]；带 value 时着色 + 色标
        coordinates = []
        values = []
        labels = []
        for point in points:
            if not isinstance(point, dict) or "x" not in point or "y" not in point:
                raise ValueError("each point must be an object with 'x' and 'y'")
            coordinates.append((float(point["x"]), float(point["y"])))
            values.append(point.get("value"))
            labels.append(str(point.get("label", "")))
        xs = [item[0] for item in coordinates]
        ys = [item[1] for item in coordinates]
        if all(item is not None for item in values):
            scatter = ax.scatter(xs, ys, s=42, c=[float(item) for item in values],
                                 cmap="viridis", edgecolor="white", linewidth=0.7)
            figure_colorbar = fig.colorbar(scatter, ax=ax, fraction=0.046, pad=0.03)
            figure_colorbar.set_label(data["units"].get("value", "value"))
        else:
            ax.scatter(xs, ys, s=42, color="#0072B2",
                       edgecolor="white", linewidth=0.7)
        for (x, y), label in zip(coordinates, labels):
            if label:
                ax.annotate(label, (x, y), textcoords="offset points",
                            xytext=(0, 7), ha="center", fontsize=7)
    else:
        raise ValueError(
            "spatial_map input requires 'points' (x/y objects) or 'grid' (values matrix)"
        )
    # 叠加参考点位（栅格形态下标注关键设施/观测点）
    if isinstance(points, list) and isinstance(grid, dict):
        for point in points:
            ax.scatter([float(point["x"])], [float(point["y"])],
                       marker="^", s=46, color="#D55E00",
                       edgecolor="white", linewidth=0.8, zorder=3)
            label = point.get("label")
            if label:
                ax.annotate(str(label), (float(point["x"]), float(point["y"])),
                            textcoords="offset points", xytext=(0, 7),
                            ha="center", fontsize=7, zorder=4)
    ax.set_xlabel(data["units"].get("x", "x coordinate"))
    ax.set_ylabel(data["units"].get("y", "y coordinate"))
    ax.set_title(data.get("title", "Spatial distribution"))
    ax.grid(alpha=0.2)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="spatial_map", drawer=_draw)
