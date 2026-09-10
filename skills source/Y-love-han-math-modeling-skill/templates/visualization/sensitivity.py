from __future__ import annotations
from .plotting_common import save_figure, _series


def _draw(fig, data):
    ax = fig.add_subplot(111)
    tornado = data.get("sensitivity")
    baseline_value = data.get("baseline")
    if isinstance(tornado, dict) and tornado:
        # 龙卷风图：每个参数给出 [low, high] 双端扰动对基准值的影响幅度
        pairs = []
        for name, rng in tornado.items():
            if (not isinstance(rng, (list, tuple)) or len(rng) != 2):
                raise ValueError(
                    f"sensitivity[{name!r}] must be [low, high]"
                )
            low, high = float(rng[0]), float(rng[1])
            base = float(baseline_value) if baseline_value is not None else 0.0
            pairs.append((str(name), low - base, high - base))
        pairs.sort(key=lambda item: abs(item[2] - item[1]), reverse=True)
        labels = [p[0] for p in pairs]
        lows = [p[1] for p in pairs]
        highs = [p[2] for p in pairs]
        ypos = range(len(pairs))
        for i, (lo, hi) in enumerate(zip(lows, highs)):
            left, right = min(lo, hi), max(lo, hi)
            ax.barh(i, right - left, left=left, height=0.62,
                    color="#0072B2", alpha=0.85)
        # low/high 已相对基准值中心化，基线恒在 0
        ax.axvline(0.0, color="#D55E00", linewidth=1.3,
                   linestyle="--", label="baseline")
        ax.legend(frameon=False, fontsize=8)
        ax.set_yticks(list(ypos))
        ax.set_yticklabels(labels, fontsize=8.5)
        ax.set_xlabel(data["units"].get("y", "output change"))
        ax.set_title("Tornado sensitivity (sorted by span)")
        ax.invert_yaxis()
        return

    effects = data.get("effects")
    if isinstance(effects, dict) and effects:
        items = sorted(effects.items(), key=lambda kv: abs(float(kv[1])),
                       reverse=True)
        labels = [str(k) for k, _ in items]
        values = [float(v) for _, v in items]
    else:
        x, y = _series(data)
        order = sorted(range(len(y)), key=lambda i: abs(y[i]), reverse=True)
        labels = [str(x[i]) for i in order]
        values = [y[i] for i in order]
    colors = ["#D55E00" if v >= 0 else "#0072B2" for v in values]
    ax.bar(labels, values, color=colors, edgecolor="white", linewidth=0.6)
    ax.axhline(0.0, color="#555555", linewidth=0.9)
    ax.set_title("Sensitivity ranking (|effect| descending)")
    ax.set_xlabel(data["units"].get("x", "factor"))
    ax.set_ylabel(data["units"].get("y", "effect (unit)"))
    ax.tick_params(axis="x", rotation=35)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="sensitivity", drawer=_draw)
