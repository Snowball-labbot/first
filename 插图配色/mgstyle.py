# -*- coding: utf-8 -*-
"""
mgstyle —— 顶刊配色库 + C 题（微网电力调度）专用绘图样式

## 配色来源说明
知乎那篇《顶刊高质量论文插图配色》是用 MATLAB 爬了上万张 PNAS / Nature / Science
插图提取的主色。本项目没拿到原图，因此改用**同来源、HEX 经过验证的标准学术色板**：
ggsci 收录的 Nature(npg) / Science(aaas) / Lancet / NEJM / PNAS 色板。
这些是顶刊论文实际在用的颜色，比凭空挑色可靠。

## 关于 C 题的语义配色
电力场景有强语义，颜色要和"物理含义"绑定，全篇统一：
    光伏 = 琥珀金（太阳）   负载 = 深蓝（需求）   电价 = 砖红（成本）
    购电 = 青              储能 SOC = 紫          充电 = 绿  放电 = 橙
    紧急购电 = 警示红       弃电 = 灰
这样评委看任何一张图，不用读图例也能反应过来是什么量。

用法：
    from mgstyle import set_style, C, PALETTES, CMAP, savefig
    set_style()                    # 一键套用（含中文字体）
    ax.plot(x, y, color=C['光伏'])
    savefig('问题1_日内曲线')
"""
from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

# ==================================================================
# 1. 顶刊标准色板（HEX 已验证，可直接用）
# ==================================================================
PALETTES = {
    # Nature 系列（npg）—— 最百搭，辨识度高且不刺眼
    "nature": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F",
               "#8491B4", "#91D1C2", "#DC0000", "#7E6148", "#B09C85"],
    # Science（aaas）—— 对比更强，适合多系列折线
    "science": ["#3B4992", "#EE0000", "#008B45", "#631879", "#008280",
                "#BB0021", "#5B90BF", "#6F6F6F", "#B2B200", "#EDAD08"],
    # Lancet —— 医学顶刊，深蓝+正红，稳重
    "lancet": ["#00468B", "#ED0000", "#42B540", "#0099B4", "#925E9F",
               "#FDAF91", "#AD002A", "#ADB6B6"],
    # NEJM —— 低饱和，适合大面积填充
    "nejm": ["#BC3C29", "#0072B5", "#E18727", "#20854E", "#7876B1",
             "#6F99AD", "#EE4C97", "#FFDC91"],
    # PNAS —— 砖红/青/金，与电力场景天然契合
    "pnas": ["#B24745", "#00A0B0", "#E4A34A", "#4A7B9D", "#87B24A",
             "#6A5A8C", "#C65146", "#8C8C8C"],
    # 低饱和柔和色（适合堆叠图、多类别填充，不刺眼）
    "soft": ["#8DA0CB", "#FC8D62", "#66C2A5", "#E78AC3", "#A6D854",
             "#FFD92F", "#E5C494", "#B3B3B3"],

    # ========= 知乎《顶刊高质量论文插图配色》6 图实测提取（slandarer） =========
    # 图1（Nature 流行病学）：中灰→砖粉→粉→橙→芥末黄→米黄，超柔和暖色系
    "zhihu1_暖灰": ["#979998", "#C69287", "#E79A90", "#EFBC91",
                    "#E4CD87", "#FAE5B8", "#DDDDDF"],
    # 图2（环形分类图）：紫→蓝→红→黄 12 色渐变家族，适合大面积分类填充
    "zhihu2_蓝红黄": ["#8074C8", "#7895C1", "#A8CBDF", "#D6EFF4", "#F2FAFC",
                      "#992224", "#B54764", "#E3625D", "#EF8B67",
                      "#F0C284", "#F5EBAE", "#F7FBC9"],
    # 图3（Nature 散点/柱状/热图）：亮金+深灰+酒红+墨紫+钢蓝，对比强烈
    "zhihu3_对比": ["#FFC04D", "#606060", "#82093B", "#34183E",
                    "#4D779B", "#C45C69", "#CD3B42", "#585D5E"],
    # 图4（PNAS 散点回归）：砖红+深紫+陶土+灰绿+皇家蓝，最有"顶刊味"的一套
    "zhihu4_pnas": ["#8D2F25", "#4E1945", "#CB9475", "#8CBF87",
                    "#3E608D", "#909291"],
    # 图5（柔和柱状+散点）：浅紫/灰/杏/浅蓝/浅粉，极低饱和
    "zhihu5_柔和": ["#B7B7EB", "#9D9EA3", "#EAB883", "#9BBBE1", "#F09BA0"],
    # 图6（散点/柱状/雷达）：蓝灰+亮紫+亮蓝+陶土红+草绿
    "zhihu6_明快": ["#A5AEB7", "#925EB0", "#7E99F4", "#CC7C71", "#7AB656"],
}

# ==================================================================
# 2. C 题（微网）语义配色 —— 全篇统一，不要每张图换色
# ==================================================================
C = {
    # 核心物理量 —— 颜色取自知乎 6 图实测色
    "光伏":   "#F0C284",   # 琥珀金(图2) —— 太阳/发电；线条版用 #E8A33D 更醒目
    "负载":   "#3E608D",   # 皇家蓝(图4) —— 需求
    "电价":   "#8D2F25",   # 深砖红(图4) —— 成本
    "购电":   "#4D779B",   # 钢蓝(图3)   —— 外网购入
    "净负载": "#7895C1",   # 中蓝(图2)   —— 负载-光伏
    # 储能
    "储能":   "#8074C8",   # 紫(图2)     —— SOC 曲线
    "充电":   "#7AB656",   # 草绿(图6)   —— 充入
    "放电":   "#EF8B67",   # 橙(图2)     —— 放出
    # 费用/异常
    "紧急":   "#992224",   # 深红(图2)   —— 5 倍电价紧急购电
    "调整":   "#925EB0",   # 亮紫(图6)   —— 日内调整量
    "弃电":   "#A5AEB7",   # 蓝灰(图6)   —— 弃光/未利用
    "计划":   "#7895C1",   # 中蓝(图2)   —— 计划值（虚线）
    "实际":   "#CD3B42",   # 正红(图3)   —— 实际值（实线）
    # 辅助
    "基线":   "#9D9EA3",   # 灰(图5)     —— 对照基线（如无储能）
    "参考":   "#606060",   # 深灰(图3)   —— 参考线
    "高亮":   "#FFC04D",   # 亮金(图3)   —— 关键点强调
}

# 线条用替代色：大面积填充用浅色，线条用同系深色（顶刊惯例）
LINE = {
    "光伏": "#E8A33D",   # 线条比填充 #F0C284 深，投影时可读
    "负载": "#2C4A75",
    "电价": "#8D2F25",
    "购电": "#3A6285",
    "储能": "#6658B0",
}

# 语义色 → 绘图用简写（方便 plt.plot 直接取）
PV, LOAD, PRICE = C["光伏"], C["负载"], C["电价"]
BUY, SOC, EMERG = C["购电"], C["储能"], C["紧急"]
CHG, DIS, CURT = C["充电"], C["放电"], C["弃电"]

# ==================================================================
# 3. 连续色标（colormap）
# ==================================================================
def _cmap(name: str, colors: list[str]) -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list(name, colors, N=256)


CMAP = {
    # 电价：低=米黄 → 高=深红（"贵"的直觉）。渐变取自知乎图2 的红黄家族
    "price":  _cmap("price",  ["#FDF9EE", "#F7FBC9", "#F5EBAE", "#F0C284",
                               "#EF8B67", "#E3625D", "#B54764", "#992224"]),
    # 光伏：无=深夜蓝 → 强=亮金。呼应"白天发电"
    "pv":     _cmap("pv",     ["#34183E", "#3E608D", "#7895C1", "#A8CBDF",
                               "#F5EBAE", "#F0C284", "#FFC04D"]),
    # 负载：低=近白 → 高=墨蓝
    "load":   _cmap("load",   ["#F5F8FB", "#D6EFF4", "#A8CBDF", "#7895C1",
                               "#3E608D", "#34183E"]),
    # SOC：低=浅紫 → 高=深紫（取自图2/图5 紫系）
    "soc":    _cmap("soc",    ["#F3F1FA", "#B7B7EB", "#8074C8", "#4E1945"]),
    # 净负载（双向）：负=中蓝（光伏盈余） 0=白 正=正红（缺口）
    "net":    _cmap("net",    ["#3E608D", "#7895C1", "#D6EFF4", "#FDFDFD",
                               "#F5EBAE", "#E3625D", "#992224"]),
    # 通用发散（蓝↔红）
    "div":    _cmap("div",    ["#3E608D", "#A8CBDF", "#F5F8FB", "#EF8B67", "#8D2F25"]),
    # 误差/残差（灰→亮金，呼应图3 散点中的 Spike-in 高亮手法）
    "accent": _cmap("accent", ["#585D5E", "#909291", "#EFBC91", "#FFC04D"]),
}


def diverging_cmap(low="#008280", mid="#FFFFFF", high="#B24745", name="div2"):
    """自定义发散色标（负=low，0=mid，正=high）。用于误差、偏差图。"""
    return _cmap(name, [low, mid, high])


# ==================================================================
# 4. 统一样式
# ==================================================================
_CN_FONTS = ["Microsoft YaHei", "SimHei", "SimSun", "Source Han Sans SC",
             "Noto Sans CJK SC", "DengXian", "KaiTi", "FangSong"]


def set_style(dpi: int = 150, font_size: float = 10.5, palette: str = "nature"):
    """一键套用出版级样式。返回识别到的中文字体名（None 表示未找到）。"""
    cn = None
    try:
        from matplotlib import font_manager
        avail = {f.name for f in font_manager.fontManager.ttflist}
        for f in _CN_FONTS:
            if f in avail:
                cn = f
                break
    except Exception:
        pass

    # 中文字体放最前构建 fallback 链（经 serif 别名引用时 fallback 不生效）
    fam = ([cn] if cn else []) + ["Arial", "Times New Roman", "DejaVu Sans"]
    plt.rcParams.update({
        "font.family": fam,
        "font.size": font_size,
        "axes.unicode_minus": False,          # 负号不显示成方块
        "mathtext.fontset": "stix",

        # 画布
        "figure.dpi": dpi,
        "savefig.dpi": 300,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",

        # 坐标轴线宽（顶刊偏细）
        "axes.linewidth": 0.9,
        "axes.edgecolor": "#333333",
        "axes.labelcolor": "#222222",
        "axes.labelsize": font_size + 1,
        "axes.titlesize": font_size + 2,
        "axes.titleweight": "bold",
        "axes.titlepad": 9,

        # 刻度：朝内是顶刊/科技论文常见做法
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.major.size": 4,
        "ytick.major.size": 4,
        "xtick.minor.size": 2.2,
        "ytick.minor.size": 2.2,
        "xtick.major.width": 0.9,
        "ytick.major.width": 0.9,
        "xtick.labelsize": font_size - 0.5,
        "ytick.labelsize": font_size - 0.5,
        "xtick.color": "#333333",
        "ytick.color": "#333333",

        # 图例：不要边框
        "legend.frameon": False,
        "legend.fontsize": font_size - 0.5,
        "legend.labelspacing": 0.4,
        "legend.handlelength": 1.6,

        # 网格：极淡，只在 y 轴
        "axes.grid": True,
        "grid.color": "#E6E6E6",
        "grid.linewidth": 0.6,
        "grid.alpha": 0.85,

        # 线条
        "lines.linewidth": 1.6,
        "lines.markersize": 5,
        "lines.markeredgewidth": 0.8,

        # 颜色循环
        "axes.prop_cycle": mpl.cycler(color=PALETTES[palette]),

        # 保存
        "savefig.bbox": "tight",
        "savefig.transparent": False,
    })
    return cn


def style_axes(ax, xlabel=None, ylabel=None, title=None, legend=True,
               grid_axis="y", minor_ticks=True, fs=None):
    """美化单个坐标轴：去上/右边框、标签、淡网格、可选次级刻度。"""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.9)
    ax.spines["bottom"].set_linewidth(0.9)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title, pad=10, fontweight="bold")
    if minor_ticks:
        try:
            ax.minorticks_on()
        except Exception:
            pass
    ax.grid(True, axis=grid_axis, color="#E6E6E6", lw=0.6, alpha=0.85, zorder=0)
    ax.set_axisbelow(True)
    if legend and ax.get_legend_handles_labels()[0]:
        ax.legend(loc="best", frameon=False)
    if fs:
        ax.tick_params(labelsize=fs)
        if xlabel:
            ax.xaxis.label.set_size(fs + 1)
        if ylabel:
            ax.yaxis.label.set_size(fs + 1)
        if title:
            ax.title.set_size(fs + 2)
        if ax.get_legend() is not None:
            for t in ax.get_legend().get_texts():
                t.set_fontsize(fs)
    return ax


def newfig(figsize=(7.2, 4.4), nrows=1, ncols=1, **kw):
    return plt.subplots(nrows, ncols, figsize=figsize, **kw)


def savefig(fig, name: str, outdir="figures", close=True):
    """保存 SVG + 300dpi PNG 双版本。返回 PNG 路径。"""
    from pathlib import Path
    d = Path(outdir)
    d.mkdir(parents=True, exist_ok=True)
    svg, png = d / f"{name}.svg", d / f"{name}.png"
    fig.savefig(svg, format="svg", bbox_inches="tight")
    fig.savefig(png, format="png", dpi=300, bbox_inches="tight")
    if close:
        plt.close(fig)
    print(f"[mgstyle] {name}.svg + .png (300dpi)")
    return png


# ==================================================================
# 5. C 题专用：能量平衡堆叠图配色（按语义固定顺序）
# ==================================================================
def energy_stack():
    """能量供给堆叠图的推荐配色顺序（光伏 → 储能放电 → 购电 → 紧急购电）。
    固定顺序 = 固定颜色，全篇一致。
    """
    return [C["光伏"], C["放电"], C["购电"], C["紧急"]]


def palette(name: str = "nature", n: int | None = None):
    """取色板。n 指定取前 n 个颜色。"""
    p = PALETTES[name]
    return p[:n] if n else p


def show_palettes(outdir="figures"):
    """画一张色卡总览图，方便队内选色。"""
    set_style()
    names = list(PALETTES)
    fig, axes = plt.subplots(len(names) + 1, 1,
                             figsize=(8.4, 0.62 * (len(names) + 1) + 1.1))
    for i, nm in enumerate(names):
        ax = axes[i]
        cols = PALETTES[nm]
        ax.imshow([list(range(len(cols)))], aspect="auto",
                  cmap=_cmap(nm, cols))
        ax.set_xticks(range(len(cols)))
        ax.set_xticklabels([c.replace("#", "") for c in cols],
                           fontsize=7.2, rotation=0)
        ax.set_yticks([])
        ax.set_ylabel(nm, rotation=0, ha="right", va="center",
                      fontsize=10, fontweight="bold")
        ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(False)
    # 最后一行：C 题语义色
    ax = axes[-1]
    keys = list(C)
    cols = [C[k] for k in keys]
    ax.imshow([list(range(len(cols)))], aspect="auto", cmap=_cmap("c", cols))
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(keys, fontsize=8)
    ax.set_yticks([])
    ax.set_ylabel("C题语义", rotation=0, ha="right", va="center",
                  fontsize=10, fontweight="bold")
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.suptitle("配色总览（上方为顶刊标准色板，最下一行为 C 题语义色）",
                 fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    return savefig(fig, "00_配色总览", outdir=outdir, close=False)


if __name__ == "__main__":
    cn = set_style()
    print("中文字体:", cn or "未找到（图中中文会变方块）")
    print("可用色板:", list(PALETTES))
    print("C题语义色:", C)
    show_palettes()
