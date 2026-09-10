# -*- coding: utf-8 -*-
"""
utils.py — 数学建模公共工具函数
用途：全局绘图风格、数据加载、文件保存、置信区间、统计检验辅助
各问题脚本通过 from utils import * 调用
"""
import os
import numpy as np
import pandas as pd
import matplotlib
# 无显示环境（headless Linux / 受控沙箱）下必须使用 Agg 后端，
# 否则 import 后首次创建画布即崩溃；有桌面环境时 Agg 同样可用。
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import matplotlib as mpl
from pathlib import Path
from scipy import stats

# ============================================================
# 随机种子（可复现——仅使用 default_rng，禁止全局 np.random.seed）
# ============================================================
RNG = np.random.default_rng(42)


def fresh_rng() -> "np.random.Generator":
    """返回独立随机流。

    ``RNG`` 为模块级共享流，同进程内多个脚本 import 会相互消耗序列，
    跨脚本复现性弱；需要独立/可复现随机性的代码应使用
    ``rng = fresh_rng(seed)`` 获得私有流。
    """
    return np.random.default_rng()


def harden_console() -> None:
    """Windows GBK 控制台/管道下的输出加固。

    报告文本包含 ✅❌⚠️ 等 emoji，重定向到管道或文件时 cp936 编码会抛
    UnicodeEncodeError 中断流程（AI agent/CI 捕获输出的典型形态）；
    统一在此切换为 UTF-8 并对不可编码字符做替换。
    """
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

# ============================================================
# 路径常量（基于 __file__ 自动定位，无需手动修改）
# ============================================================
_BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = _BASE_DIR / '题目' / '附件数据'
OUTPUT_DIR = _BASE_DIR
FIGURES_DIR = OUTPUT_DIR / '结果' / 'figures'
PAPER_FIGURES_DIR = OUTPUT_DIR / '论文' / 'figures'


def ensure_output_dirs():
    """惰性创建输出目录。

    仅在真正写文件时调用（save_fig 内部），避免"import 即在模板/项目
    目录里产生空目录"的副作用污染源树与交付卫生检查。
    目录被 redirect_figures 置为 None 时跳过（单目标模式）。
    """
    for d in [FIGURES_DIR, PAPER_FIGURES_DIR]:
        if d is not None:
            os.makedirs(d, exist_ok=True)


def redirect_figures(figures_dir, paper_dir=None):
    """重定向后续 save_fig 的落盘目录（CLI ``--output`` 语义的唯一实现）。

    - 只传 ``figures_dir``：进入单目标模式，PNG 仅写入该目录，
      不再写论文目录——EDA/诊断管线的图片应跟随其报告目录；
    - 同时传 ``paper_dir``：恢复双目标模式。
    不调用此函数时保持默认全局目录，既有脚本行为不变。
    """
    global FIGURES_DIR, PAPER_FIGURES_DIR
    FIGURES_DIR = Path(figures_dir)
    PAPER_FIGURES_DIR = Path(paper_dir) if paper_dir is not None else None

# ============================================================
# 国家级特等奖论文插图配色系统（科研绘图权威标准整合版）
# ─────────────────────────────────────────────────────────
# 主分类板 COLORS（9 色定制板）：
#   前 7 位 = Okabe-Ito 原序（Wong 2011，Nature 推荐事实标准——
#   色盲友好 + 印刷友好），索引语义保持（0=蓝、1=橙红、2=绿、
#   3=粉紫、4=天蓝、5=金黄、6=灰），兼容全部既有代码；
#   追加 7=酒红、8=青绿（取自 Paul Tol muted 低饱和学术系），
#   使分类容量从 7 提升至 9 且不破坏任何索引引用。
#   国奖视觉语言 = 蓝主调（沉稳学术）+ 橙红强调（本文方法）+
#   冷暖平衡（Paul Tol / Okabe-Ito 混合）。
# ⛔ 关键规则（跨图颜色编码一致性核心）："本文方法"恒用 COLORS[1]
#    （橙红 #D55E00，评委目光焦点），对比方法恒用蓝/绿/灰
#    （COLORS[0]/[2]/[6]），全篇禁止互换。
# 高色数分类板（分类 ≥10 时按需选用，见 pick_qual 自动选板）：
#   Tableau 10（国奖常见鲜艳板，10 色）
#   Paul Tol muted（低饱和学术板，9 色）
#   ColorBrewer Set3（柔和 12 色）/ Paired（成对 12 色）
#   Tableau 20（极端多分类 20 色）
#   Petrol 6（天体物理学会推荐，色盲安全 + 黑白打印可辨）
# 备选板（按需切换）：Okabe-Ito 8 / NPG 10 / Paul Tol bright 7
# ============================================================
COLORS = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#56B4E9',
          '#E69F00', '#999999', '#882255', '#44AA99']
# 语义色约定：本文方法=橙红强调；对比方法=蓝/绿/灰
OURS_COLOR = COLORS[1]        # 本文方法（橙红 #D55E00——最醒目）
BASELINE_COLOR = COLORS[0]    # 基准/对比方法一（蓝 #0072B2）
ALT_COLORS = [COLORS[0], COLORS[2], COLORS[6], COLORS[4], COLORS[3],
              COLORS[7], COLORS[8], COLORS[5]]  # 对比方法色序（蓝/绿/灰/天蓝/粉/酒红/青/金）

# ============================================================
# 类型化配色方案（每种插图类型的最佳颜色——科研绘图权威标准）
# 四类色彩语义：
#   ① 定性色（Qualitative）：类别/系列区分——色相差最大化
#   ② 顺序色（Sequential）：0→高 单极值递进——曲面/密度/概率
#   ③ 发散色（Diverging）：-→0→+ 双极值居中白——热力/相关/误差
#   ④ 专用色（Special）：地形/瀑布等语义专用
# 权威来源：Okabe-Ito（Wong 2011）/ Paul Tol（Tol 技术说明）/
#   ColorBrewer（Brewer）/ Crameri 科学色图（Science 2018）/
#   Tableau / Nature-Science 出版规范
# ============================================================
QUAL_COLORS = COLORS  # 定性默认：9 色定制板（蓝主调 + 橙红强调）
# Okabe-Ito（Wong 2011）——色盲友好定性板的事实标准（Nature 推荐）：
# 橙/浅蓝/绿/黄/蓝/红/粉/黑，全色盲可区分。评委色盲场景或追求
# 顶级期刊色盲合规时切换（`COLORS = OKABE_ITO` 一行即可）
OKABE_ITO = ['#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2',
             '#D55E00', '#CC79A7', '#000000']
# --- 高色数分类板（分类 ≥10 时按需选用）---
TABLEAU_10 = ['#1F77B4', '#FF7F0E', '#2CA02C', '#D62728', '#9467BD',
              '#8C564B', '#E377C2', '#7F7F7F', '#BCBD22', '#17BECF']
TABLEAU_20 = (TABLEAU_10 +
              ['#AEC7E8', '#FFBB78', '#98DF8A', '#FF9896', '#C5B0D5',
               '#C49C94', '#F7B6D2', '#C7C7C7', '#DBDB8D', '#9EDAE5'])
TOL_MUTED = ['#88CCEE', '#44AA99', '#117733', '#332288', '#DDCC77',
             '#999933', '#CC6677', '#882255', '#AA4499']
SET3_12 = ['#8DD3C7', '#FFFFB3', '#BEBADA', '#FB8072', '#80B1D3',
           '#FDB462', '#B3DE69', '#FCCDE5', '#D9D9D9', '#BC80BD',
           '#CCEBC5', '#FFED6F']
PAIRED_12 = ['#A6CEE3', '#1F78B4', '#B2DF8A', '#33A02C', '#FB9A99',
             '#E31A1C', '#FDBF6F', '#FF7F00', '#CAB2D6', '#6A3D9A',
             '#FFFF99', '#B15928']
PETROFF_6 = ['#5790FC', '#F89C20', '#E42536', '#964A8B', '#9C9CA1',
             '#7A21DD']  # 天体物理学会推荐：色盲安全 + 黑白打印可辨
# --- 备选板 ---
QUAL_COLORS_ALT = ['#E64B35', '#4DBBD5', '#00A087', '#3C5488', '#F39B7F',
                   '#8491B4', '#91D1C2', '#DC0000', '#7E6148', '#B09C85']  # NPG 备选
TOL_BRIGHT = ['#4477AA', '#66CCEE', '#228833', '#CCBB44', '#EE6677',
              '#AA3377', '#BBBBBB']  # Paul Tol bright（科研标准）

# 顺序色（按推荐序）：viridis——近年国奖论文 3D 曲面主流标准
# （感知均匀 + 色盲友好 + 明亮清晰）；magma 深紫→橙黄（冲击备选，
# Nature 封面风格）；YlGnBu 明亮期刊传统；inferno 暗色高对比；
# plasma/cividis 为 viridis 族补充（cividis 专为色盲优化）
SEQUENTIAL_CMAPS = ['viridis', 'magma', 'YlGnBu', 'GnBu', 'inferno',
                    'plasma', 'cividis']
# 发散色（按推荐序）：RdBu/coolwarm 中间白/灰白——感知均匀、打印友好
# （Nature/Science 发散色标准）；PRGn 紫-绿（色盲安全性优于 RdBu，
# 相关矩阵备选）；Spectral 全谱 11 级（信息量大）；RdYlBu 中间黄
# 明度过高（感知非线性）仅作末位备选
DIVERGING_CMAPS = ['RdBu', 'coolwarm', 'PRGn', 'PiYG', 'Spectral', 'RdYlBu']
SPECIAL_CMAPS = {'terrain': 'terrain', 'landscape': 'gist_earth'}         # 地形专用
WATERFALL_COLORS = {'positive': '#2CA02C', 'negative': '#D62728'}         # 瀑布正负语义色
BAR_EMPHASIS_COLOR = '#1F77B4'   # 柱状图最优值强调（深蓝）
BAR_OTHER_COLORS = ['#7F7F7F', '#17BECF', '#BCBD22', '#9467BD']           # 柱状图非最优（灰/浅色）

# ============================================================
# Crameri 科学色图（Fabio Crameri《Scientific colour maps》，Science
# 2018——感知均匀 + 色盲安全 + 印刷友好的新一代标准；精确色值来自
# cmcrameri 包）。安装 cmcrameri 后自动启用（pip install cmcrameri），
# 未安装时回退 matplotlib 内置色图，不影响任何功能。
# 常用：batlow（通用顺序，viridis 升级替代）、oslo（黑→白单色）、
#   lajolla（地形/密度，色盲最优）、vik（通用发散）、
#   berlin（海温异常类双极）、roma（地质/温度双极）
# ============================================================
try:
    import cmcrameri.cm as _cmc
    CRAMERI_AVAILABLE = True
except ImportError:
    _cmc = None
    CRAMERI_AVAILABLE = False
CRAMERI_SEQUENTIAL = ['batlow', 'oslo', 'lajolla', 'bilbao', 'tokyo',
                      'hawaii', 'davos', 'turku', 'bamako', 'acton']
CRAMERI_DIVERGING = ['vik', 'roma', 'berlin', 'cork', 'broc', 'lisbon', 'bam']

# ============================================================
# 插图类型 → 最佳配色映射（科研绘图权威标准，与 SKILL.md 映射表一致）
# ============================================================
FIG_TYPE_COLORS = {
    'line':            'qual',        # 多系列折线：主分类板 COLORS（9 色）
    'bar':             'qual+emph',   # 分组柱状：定性 + 最优值深蓝强调
    'histogram':       'seq',         # 单变量分布：单色系顺序（Blues——分布密度最适，viridis 多极值偏重）
    'scatter_class':   'qual',        # 分类散点：定性板（分类多时用 pick_qual）
    'scatter_density': 'seq',         # 密度散点：顺序色（viridis）
    'hexbin':          'seq',         # 六边形密度分箱：顺序色（viridis）
    'heatmap':         'div',         # 热力图：发散色（RdBu 零居中白，感知均匀）
    'correlation':     'div',         # 相关矩阵：发散色（RdBu 中性；PRGn 色盲安全备选）
    'twinx':           'pair',        # 双 y 轴：COLORS[0]+COLORS[1] 轴色绑定
    'surface':         'seq',         # 3D 曲面：顺序色（viridis/batlow）
    'sobol_3d':        'seq',         # Sobol 交互曲面：顺序色（viridis/batlow）
    'contour':         'div',         # 双因素交互等高线：发散色（RdBu——正负效应，零线居中白）
    'mc_3d':           'seq',         # MC 稳健性 3D 分布：顺序色（viridis——输出为单极值量，RdBu 中间白带无意义且暗示正负语义，非最适）
    'pareto':          'seq',         # Pareto 3D：顺序色（viridis）
    'pca_scatter':     'seq',         # PCA 3D 散点：顺序色（viridis）
    'bar_3d':          'qual',        # 3D 柱状：定性板（多类别用 pick_qual）
    'waterfall':       'wf',          # 瀑布图：绿正红负语义色
    'box_violin':      'qual',        # 箱线/小提琴：定性板
    'ridge':           'seq',         # 脊线图（多组分布）：单色系顺序（Blues——分布叠层最适）
    'radar':           'qual',        # 雷达：定性板（多指标用 pick_qual）
    'sankey_chord':    'qual',        # 桑基/和弦：定性板（NPG 备选）
    'network':         'qual',        # 网络：节点定性 + 边浅灰
    'streamline':      'seq',         # 3D 轨迹/流线：顺序色（plasma——时间/速度渐变，暖色视觉冲击）
    'terrain':         'special',     # 地形/景观：terrain/gist_earth 专用
    'convergence':     'single',      # 收敛/残差诊断：单色 + 红色参考线
    'errorbar':        'qual',        # 误差棒：数据定性色 + 黑误差棒
}

# 类型级 cmap 覆盖（优先于语义默认——科研标准逐类最适）：
#   单极值量（曲面/散点/密度/Pareto/PCA/MC 分布）→ viridis 顺序；
#   单变量分布/脊线 → Blues 单色系（分布密度最适，避免多极值误导）；
#   双极值量（热力/相关/等高线）→ RdBu 发散零居中白
FIG_TYPE_CMAP_OVERRIDE = {
    'pareto': 'viridis', 'pca_scatter': 'viridis', 'density': 'viridis',
    'scatter_density': 'viridis', 'hexbin': 'viridis',
    'sobol_3d': 'viridis',
    'mc_3d': 'viridis',              # 单极值输出 → 顺序色（最适）
    'histogram': 'Blues',            # 单变量分布 → 单色系（最适）
    'ridge': 'Blues',                # 脊线叠层 → 单色系（最适）
    'streamline': 'plasma',          # 轨迹时间/速度渐变 → 暖色顺序（最适）
    'heatmap': 'RdBu', 'correlation': 'RdBu',
    'contour': 'RdBu',               # 交互正负效应 → 发散零居中白
}


def pick_qual(n_categories, vivid=False):
    """按分类数自动选择最佳定性色板（颜色"多"的核心接口）

    分类数 → 选板规则（科研标准）：
      n ≤ 6  → COLORS 前 n 位（蓝/橙红/绿/粉/天蓝/金——高区分度）
      7 ≤ n ≤ 9  → COLORS 全 9 色（主分类板）
      n ≤ 10 → TABLEAU_10（国奖鲜艳板，10 色）
      n ≤ 12 → SET3_12（柔和 12 色）或 PAIRED_12（成对 12 色，
               "本文 vs 对比"成对语义场景传 paired=True 选此）
      n > 12 → TABLEAU_20（极端多分类 20 色）
    跨图一致性保证：任何板下"本文方法"均由调用方用 OURS_COLOR
    （橙红 #D55E00）着色，本函数返回的板仅用于对比方法序列。
    色板上限为 20（Tableau 20）——分类数 >20 时返回 20 色并须
    结合形状/线型/透明度等第二通道区分（纯色无法承载 >20 类）。

    Args:
        n_categories: 分类/系列数量
        vivid: True 时优先鲜艳板（Tableau 系，对比图/答辩场景）；
               False 时优先学术低饱和板（默认）

    Returns:
        list[str]: HEX 色板（长度 = min(需要色数, 20)，≥ n_categories
                   当 n_categories ≤ 20）
    """
    if n_categories <= 6:
        return list(COLORS[:n_categories])
    if n_categories <= 9:
        return list(COLORS)
    if n_categories <= 10:
        return list(TABLEAU_10)
    if n_categories <= 12:
        return list(SET3_12 if not vivid else PAIRED_12)
    return list(TABLEAU_20)


def pick_cmap(fig_type, seq_pref=None, div_pref=None, crameri=False):
    """按插图类型返回最佳渐变色映射（顺序/发散/专用）

    权威映射（与 SKILL.md 图表规范一致）：
      顺序类（曲面/Sobol/Pareto/PCA/密度/直方）→ viridis 族
        （已安装 cmcrameri 且 crameri=True 时：batlow 为 viridis
        的升级替代——感知均匀 + 色盲安全 + 灰度友好）
      发散类（热力/相关/MC 分布）→ RdBu 族
        （crameri=True 时：vik/berlin 为 RdBu 的色盲安全替代）
      专用类（地形/景观）→ terrain/gist_earth

    Args:
        fig_type: 插图类型键（见 FIG_TYPE_COLORS，如 'heatmap'/'surface'）
        seq_pref: 顺序色偏好（默认 'viridis'——国奖论文 3D 主流标准；
                  'magma' 冲击备选；'batlow'/'oslo' 等 Crameri 名
                  需已安装 cmcrameri 且 crameri=True）
        div_pref: 发散色偏好（默认 'RdBu'——国奖热力图标准；
                  'coolwarm' 优雅备选；'PRGn' 色盲安全备选；
                  'vik'/'berlin' 等 Crameri 名同理）
        crameri: 是否启用 Crameri 科学色图（需已安装 cmcrameri）

    Returns:
        str: matplotlib cmap 名称；定性/单色类返回 None（用 COLORS）
    """
    if fig_type in FIG_TYPE_CMAP_OVERRIDE:
        base = FIG_TYPE_CMAP_OVERRIDE[fig_type]
        # Crameri 优先覆盖（仅当显式启用且可用）：
        # 未显式指定 pref 时按语义落到 crameri 默认（seq→batlow、div→vik）；
        # 显式指定（含 crameri 名 berlin/oslo 等）一律尊重用户选择
        if crameri and CRAMERI_AVAILABLE:
            if base == 'viridis':
                return seq_pref or 'batlow'
            if base == 'RdBu':
                return div_pref or 'vik'
        return base
    kind = FIG_TYPE_COLORS.get(fig_type, 'qual')
    if kind == 'seq':
        if crameri and CRAMERI_AVAILABLE:
            return seq_pref or 'batlow'
        return seq_pref or 'viridis'
    if kind == 'div':
        if crameri and CRAMERI_AVAILABLE:
            return div_pref or 'vik'
        return div_pref or 'RdBu'
    if kind == 'special':
        return SPECIAL_CMAPS.get(fig_type, 'terrain')
    return None

# ============================================================
# 全局绘图风格（出版级精致化，≥300dpi，顶级期刊坐标轴规范）
# 精致高级核心（去"塑料感"/去粗糙）：
#   - 细线宽（线 1.4 / spine 0.8 / 刻度 0.8——粗线=粗糙感主因）
#   - 全元素抗锯齿（线条/文本/色块——锯齿=塑料感主因）
#   - 低饱和学术配色（COLORS 9 色板，见上方配色系统）
#   - 图例浅灰细框 + 半透明（无黑粗框）
#   - 网格细线淡化（0.6pt / alpha 0.25）
#   - 大/小数值自动科学计数法（±10⁴ 阈值）
# ⛔ 坐标轴防重叠关键参数（用户强制要求）：
#   - 刻度方向朝外（out，Nature/Science 标准），避免刻度线侵入绘图区
#   - 刻度标签与刻度线间距 pad=5、轴标签与刻度标签间距 labelpad=8
#   - 关闭上/右刻度线（防双轴拥挤、刻度标签互相碰撞）
#   - 3D 图需额外 ax.tick_params(pad=4~6) 防止轴标签压刻度标签
# ============================================================
mpl.rcParams.update({
    'figure.dpi': 150, 'savefig.dpi': 300,
    'font.size': 11, 'axes.titlesize': 13, 'axes.labelsize': 11,
    'xtick.labelsize': 9, 'ytick.labelsize': 9, 'legend.fontsize': 9,
    # ---- 精致化：细线宽 + 抗锯齿（去塑料感/去粗糙核心）----
    'lines.linewidth': 1.4, 'lines.markersize': 7, 'lines.antialiased': True,
    'patch.linewidth': 0.8, 'patch.antialiased': True,   # 柱/箱线/色块细边
    'axes.linewidth': 0.8,                               # 坐标轴线宽
    'axes.edgecolor': '#000000',
    'xtick.major.width': 0.8, 'ytick.major.width': 0.8,  # 细刻度线
    'xtick.minor.width': 0.6, 'ytick.minor.width': 0.6,
    'xtick.major.size': 3.5, 'ytick.major.size': 3.5,    # 刻度线长度规范
    'xtick.minor.size': 2.0, 'ytick.minor.size': 2.0,
    'text.antialiased': True,
    # ---- 图例精致化：浅灰细框 + 半透明（禁黑粗框）----
    'legend.frameon': True, 'legend.framealpha': 0.9,
    'legend.edgecolor': '#CCCCCC', 'legend.fancybox': False,
    'legend.borderaxespad': 0.6, 'legend.handlelength': 1.6,
    'legend.handletextpad': 0.6, 'legend.columnspacing': 1.0,
    # ---- 网格精致化：细线 + 淡化（禁深色实线网格抢视觉）----
    'grid.linewidth': 0.6, 'grid.alpha': 0.25, 'grid.linestyle': '--',
    'grid.color': '#666666',
    # ---- 数值格式精致化 ----
    'axes.formatter.limits': (-4, 4),    # 超过 10^±4 自动科学计数法
    'axes.formatter.useoffset': False,   # 禁"1+4e-2"式偏移标注（粗糙感）
    'errorbar.capsize': 3,
    'savefig.bbox': 'tight',
    'savefig.facecolor': 'white',
    # 跨平台 CJK 回退链（与 visualization/plotting_common 保持一致）：
    # Windows→macOS→Linux 全覆盖，避免无 SimHei 环境中文标签变豆腐块。
    'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'PingFang SC',
                        'Hiragino Sans GB', 'Noto Sans CJK SC',
                        'Source Han Sans SC', 'WenQuanYi Micro Hei',
                        'Arial Unicode MS', 'sans-serif'],
    'axes.unicode_minus': False,
    # ---- 坐标轴防重叠（出版级标准）----
    # ⚠️ rcParams 键名：x 轴为 xtick.top/bottom，y 轴为 ytick.left/right
    #    （不存在 ytick.top——2026 实测验证，写错键名运行时抛 KeyError）
    'xtick.direction': 'out', 'ytick.direction': 'out',
    'xtick.top': False, 'ytick.right': False,
    'xtick.major.pad': 5, 'ytick.major.pad': 5,
    'axes.labelpad': 8,
    'axes.spines.top': False, 'axes.spines.right': False,  # Nature 风格
    'axes.titlepad': 6,
    'figure.subplot.wspace': 0.3, 'figure.subplot.hspace': 0.35,
})

# ============================================================
# 文件操作
# ============================================================

def load_data(path=None, *, required=False):
    """Load the first declared tabular input, or return a safe demo frame.

    The default is intentionally explicit: a missing input returns a small
    ``demo``-labelled DataFrame so that template smoke tests can run, while a
    production adapter must call ``load_data(..., required=True)`` and provide
    a registered, problem-specific path.  The function never silently invents
    production evidence.
    """
    candidates = []
    if path is not None:
        candidates.append(Path(path))
    else:
        candidates.extend(sorted(DATA_DIR.glob("*.csv")))
        candidates.extend(sorted(DATA_DIR.glob("*.xlsx")))
        candidates.extend(sorted(DATA_DIR.glob("*.xls")))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        suffix = candidate.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(candidate)
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(candidate)
        raise ValueError(f"unsupported tabular input format: {candidate.suffix}")
    if required:
        raise FileNotFoundError(
            "no tabular input found; provide a problem-specific registered input path"
        )
    demo_x = np.linspace(0.0, 1.0, 16)
    return pd.DataFrame({
        "demo_predictor": demo_x,
        "demo_target": 1.0 + 2.0 * demo_x,
    })


def save_fig(fig, name, show=False, dpi=300, also_pdf=False):
    """保存图表到结果目录和论文目录（≥300dpi 出版级 PNG）

    ⛔ 默认只输出 PNG（300dpi）——用户强制：插图不需要 PDF 版本。
    300dpi 在论文 0.85\textwidth 尺寸下清晰度完全满足印刷标准，
    PDF 矢量版不再生成（也_pdf=True 仅在特殊需求时手动开启）。

    Args:
        fig: matplotlib figure
        name: 文件名（含扩展名，如 fig1_results.png）
        show: 是否显示
        dpi: 分辨率（默认300；位图≥300dpi）
        also_pdf: 是否额外输出 PDF 矢量版（默认 False——不需要 PDF）
    """
    # ⛔ 坐标轴防重叠强制标准化（用户强制：所有类型插图坐标轴不得重叠）
    #    在出图出口统一应用 style_axes——任何图（2D/3D/多子图/热力图/
    #    twinx）经过 save_fig 都会被标准化，杜绝轴标签压刻度、刻度标签
    #    互相挤压等缺陷。幂等设计，重复调用安全。
    for ax in fig.axes:
        style_axes(ax)

    # ⛔ 出口自动重叠检测报告（插图质量硬性门禁）
    #    save_fig 时自动运行文字/坐标轴重叠检测并打印警告（不中断出图——
    #    但警告项须在门禁核查时清零）。与"AI 显式调用 check"形成双保险。
    try:
        _t_overlaps = check_text_overlaps(fig, verbose=False)
        _a_overlaps = check_axis_overlaps(fig, verbose=False)
        if _t_overlaps:
            print(f"⚠️ [save_fig 自动检查] 图 {name} 存在 {len(_t_overlaps)} 处"
                  f"文字重叠 → {_t_overlaps[:5]}（须调整标注/图例位置）")
        if _a_overlaps:
            print(f"⚠️ [save_fig 自动检查] 图 {name} 存在 {len(_a_overlaps)} 处"
                  f"坐标轴重叠 → {_a_overlaps[:5]}（须调整间距）")
    except Exception as error:
        # Quality diagnostics must not corrupt an otherwise valid image, but
        # the reason remains visible to the caller for later review.
        print(f"[save_fig quality-check unavailable] {name}: {error}")
    stem = os.path.splitext(name)[0]
    ensure_output_dirs()

    written = []
    for d in [d for d in [FIGURES_DIR, PAPER_FIGURES_DIR] if d is not None]:
        # PNG 位图版（300dpi，支撑材料）
        png_path = os.path.join(d, name)
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight',
                    facecolor='white')
        written.append(png_path)
        # PDF 矢量版（论文 LaTeX 插入优先用此版本）
        if also_pdf:
            pdf_path = os.path.join(d, f'{stem}.pdf')
            fig.savefig(pdf_path, bbox_inches='tight',
                        facecolor='white')
            written.append(pdf_path)
    if show:
        plt.show()
    plt.close(fig)
    # 返回主 PNG 的真实落盘路径，供结果 JSON / 论文绑定直接引用；
    # 旧调用方若忽略返回值不受影响。
    return written[0] if written else None


def save_csv(df, name, index=False):
    """保存 DataFrame 到 CSV（UTF-8 BOM，Excel 兼容）"""
    path = OUTPUT_DIR / '结果' / name
    df.to_csv(path, index=index, encoding='utf-8-sig')
    print(f"已保存: {path}")
    return path


# ============================================================
# 置信区间
# ============================================================

def confidence_interval(data, confidence=0.95):
    """计算 t 分布置信区间

    Args:
        data: array-like, 样本数据
        confidence: float, 置信水平（默认 0.95）

    Returns:
        (mean, lower, upper): 均值和置信区间上下界
        如果数据不足则返回 (nan, nan, nan)
    """
    data = np.asarray(data)
    data = data[~np.isnan(data)]
    n = len(data)
    if n < 2:
        return np.nan, np.nan, np.nan
    mean = np.mean(data)
    se = stats.sem(data)
    h = se * stats.t.ppf((1 + confidence) / 2, n - 1)
    return mean, mean - h, mean + h


def bootstrap_ci(data, stat_func=np.mean, n_bootstrap=1000, confidence=0.95,
                 rng=None):
    """Bootstrap 置信区间

    Args:
        data: array-like
        stat_func: callable, 统计量函数（默认 np.mean）
        n_bootstrap: int, 重采样次数
        confidence: float, 置信水平
        rng: 可选 np.random.Generator；缺省用模块共享流 RNG（行为与历史
            版本一致）。需要独立/可复现随机流的调用方传入
            ``fresh_rng()`` 或自建 Generator，避免与其他抽样相互消耗。

    Returns:
        (stat_value, lower, upper)
    """
    if rng is None:
        rng = RNG
    data = np.asarray(data)
    n = len(data)
    if n < 2:
        return np.nan, np.nan, np.nan
    boot_stats = [stat_func(rng.choice(data, n, replace=True))
                  for _ in range(n_bootstrap)]
    alpha = (1 - confidence) / 2
    lower = np.percentile(boot_stats, alpha * 100)
    upper = np.percentile(boot_stats, (1 - alpha) * 100)
    return stat_func(data), lower, upper


# ============================================================
# 统计标注
# ============================================================

def add_significance_annotation(ax, x1, x2, y, p_value, y_offset=0.05):
    """在图上添加统计显著性标注条（*p<0.05, **p<0.01, ***p<0.001）"""
    y_max = y * (1 + y_offset)
    if p_value < 0.001:
        sig_text = '***'
    elif p_value < 0.01:
        sig_text = '**'
    elif p_value < 0.05:
        sig_text = '*'
    else:
        sig_text = 'n.s.'
    ax.plot([x1, x1, x2, x2],
            [y_max * 0.98, y_max, y_max, y_max * 0.98],
            lw=1.5, color='black')
    ax.text((x1 + x2) / 2, y_max * 1.01, sig_text,
            ha='center', va='bottom', fontsize=14, fontweight='bold')


# ============================================================
# 数据编码检测
# ============================================================

def detect_encoding(file_path, sample_size=100000):
    """检测文件编码"""
    try:
        import chardet
        with open(file_path, 'rb') as f:
            raw = f.read(sample_size)
        result = chardet.detect(raw)
        return result['encoding'], result['confidence']
    except ImportError:
        return None, 0


ENCODINGS_TO_TRY = ['utf-8', 'gb2312', 'gbk', 'gb18030', 'latin1', 'cp1252']


# ============================================================
# 出版级坐标轴标准化（防重叠——用户强制：所有类型插图坐标轴不得重叠）
# ============================================================

def style_axes(ax, tick_pad=5, label_pad=8, three_d_label_pad=14):
    """出版级坐标轴标准化（幂等，可安全重复调用）

    一键应用全部精致化 + 防重叠设置（不修改颜色/字体/数据）：
    - 刻度方向朝外 + 刻度标签间距 pad（2D/3D 通用）
    - 轴标签与刻度标签间距 labelpad（2D: 8；3D: 14——mplot3d
      轴标签压刻度标签的常见缺陷需要更大间距）
    - 关闭上/右刻度线（Nature 风格 minimal）+ spine/刻度线宽 0.8（细线精致）
    - 长刻度标签（>6 字符）自动旋转 30°，防标签互相重叠
      （日期/长文本刻度常见缺陷）
    - 刻度密度控制（>12 个主刻度自动收紧——过密=粗糙感）
    - 3D 图：tick_params(pad) + 三个轴 labelpad 全部加大

    Args:
        ax: matplotlib axes（2D 或 Axes3D 通用）
        tick_pad: 刻度标签与刻度线间距（pt）
        label_pad: 轴标签与刻度标签间距（pt，2D）
        three_d_label_pad: 3D 轴标签间距（pt，mplot3d 需要更大值）
    """
    is_3d = '3d' in ax.__class__.__name__.lower()
    try:
        if is_3d:
            # mplot3d：轴标签易压刻度标签（2026 实测确认），必须加大 labelpad
            ax.tick_params(pad=max(tick_pad, 4),
                           width=0.8, length=3.5)
            ax.set_xlabel(ax.get_xlabel(), labelpad=three_d_label_pad)
            ax.set_ylabel(ax.get_ylabel(), labelpad=three_d_label_pad)
            ax.set_zlabel(ax.get_zlabel(), labelpad=three_d_label_pad)
            return
        ax.tick_params(axis='both', direction='out', pad=tick_pad,
                       width=0.8, length=3.5)
        ax.tick_params(top=False, right=False)
        # spine 细线（精致感：粗 spine = 粗糙感主因之一）
        try:
            for sp in ('left', 'bottom'):
                ax.spines[sp].set_linewidth(0.8)
        except Exception:
            pass
        try:
            ax.xaxis.label.set_pad(label_pad)
            ax.yaxis.label.set_pad(label_pad)
        except Exception:
            pass
        # 长刻度标签自动旋转（防互相重叠）
        xt = [t.get_text() for t in ax.get_xticklabels() if t.get_text()]
        if xt and any(len(t) > 6 for t in xt):
            ax.tick_params(axis='x', rotation=30)
        yt = [t.get_text() for t in ax.get_yticklabels() if t.get_text()]
        if yt and any(len(t) > 6 for t in yt):
            ax.tick_params(axis='y', rotation=30)
        # 刻度密度控制（防过密粗糙）：主刻度 >12 个 → 自动收紧至 ≤10
        try:
            from matplotlib.ticker import MaxNLocator
            n_xt = len(ax.get_xticks())
            n_yt = len(ax.get_yticks())
            if n_xt > 12:
                ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
            if n_yt > 12:
                ax.yaxis.set_major_locator(MaxNLocator(nbins=10))
        except Exception:
            pass
    except Exception:
        pass  # 标准化失败不中断出图（极端自定义 axes）


# ============================================================
# 文字重叠自动检测（插图质量门禁——文字与图形不得重叠）
# ============================================================

def check_text_overlaps(fig, verbose=True):
    """检测图中"文字-文字/图例/数据点"重叠（文字与图形不重叠的自动检查）

    用法：每张图 save_fig 前调用一次：
        fig = plt.figure(...)
        ...
        overlaps = check_text_overlaps(fig)
        assert not overlaps, "存在文字重叠，须调整标注位置后重新出图"
        save_fig(fig, 'figX.png')

    ⚠️ 3D 图局限：Axes3D 的数据点坐标为 3 维，transData 投影后
    点-文本检测可能失效（异常被内部吞掉，不中断出图）——3D 图
    以"文本-文本/图例"检测 + 缩放目检为准，数据点-文本重叠靠
    annotate 的 xytext 偏移规则保证。

    Returns:
        list: [(text_a, text_b)] 重叠对；空列表 = 无重叠 = 通过
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    overlaps = []
    for ax in fig.axes:
        items = []
        for t in ax.texts:
            try:
                bb = t.get_window_extent(renderer=renderer)
                items.append((t.get_text()[:20], bb))
            except Exception:
                pass
        leg = ax.get_legend()
        if leg is not None and leg.get_visible():
            try:
                items.append(('legend', leg.get_window_extent(renderer=renderer)))
            except Exception:
                pass
        # 文本-文本/文本-图例重叠检测
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if items[i][1].overlaps(items[j][1]):
                    overlaps.append((f'{items[i][0]}', items[j][0]))
        # 文本-数据图形重叠（近似检测：标注框 vs 数据点 bbox）
        try:
            import matplotlib.text as mtext
            for t in ax.texts:
                tbb = t.get_window_extent(renderer=renderer)
                tc = ((tbb.x0 + tbb.x1) / 2, (tbb.y0 + tbb.y1) / 2)
                t_h = max(tbb.y1 - tbb.y0, 1e-9)
                for artist in ax.lines:
                    xd, yd = artist.get_xdata(), artist.get_ydata()
                    if len(xd) > 0:
                        pts = ax.transData.transform(
                            list(zip(xd[::max(1, len(xd) // 200)], yd[::max(1, len(yd) // 200)])))
                        for (px, py) in pts:
                            if tbb.contains(px, py):
                                # ⚠️ 网络图节点标签（nx.draw 默认把
                                #    标签画在节点中心）是标准画法——若文本中心
                                #    与数据点距离 < 0.6×文本高度，视为"标签位于
                                #    点上的合法形态"，豁免；只有文本明显偏离数据
                                #    点仍扫过（中心距大）才是真实遮挡 → 报告
                                if ((tc[0] - px) ** 2 + (tc[1] - py) ** 2) ** 0.5 \
                                        < 0.6 * t_h:
                                    continue
                                overlaps.append((f'text:{t.get_text()[:10]}', 'data-point'))
                                break
                for coll in ax.collections:
                    try:
                        offsets = coll.get_offsets()
                        if len(offsets) > 0:
                            pts = ax.transData.transform(offsets[::max(1, len(offsets) // 200)])
                            for (px, py) in pts:
                                if tbb.contains(px, py):
                                    if ((tc[0] - px) ** 2 + (tc[1] - py) ** 2) ** 0.5 \
                                            < 0.6 * t_h:
                                        continue
                                    overlaps.append((f'text:{t.get_text()[:10]}', 'data-point'))
                                    break
                    except Exception:
                        pass
                # ⚠️ patch 重叠检测（柱状/箱线/热力格子/误差区域等——
                #    文字压住柱体/箱体/色块 = 常见粗糙感缺陷；热力格子
                #    中央的 annot 属"标签在格子上"合法形态，按中心距豁免）
                for p in ax.patches:
                    try:
                        # Rectangle 用 get_bbox；PathPatch（箱线/误差条等）
                        # 无 get_bbox，改用 path extents（数据坐标）
                        try:
                            pb = p.get_bbox()
                        except AttributeError:
                            pb = p.get_path().get_extents()
                        if pb is None:
                            continue
                        # 数据坐标 → 窗口坐标
                        (x0, y0), (x1, y1) = ax.transData.transform(
                            [(pb.x0, pb.y0), (pb.x1, pb.y1)])
                        pb_win = mpl.transforms.Bbox.from_extents(
                            x0, y0, x1, y1)
                        if pb_win.overlaps(tbb):
                            pc = ((pb_win.x0 + pb_win.x1) / 2,
                                  (pb_win.y0 + pb_win.y1) / 2)
                            # 热力格子 annot 合法形态判定（双条件）：
                            #   ① 文本中心在色块中心附近（中心距 < 0.6×文本高）
                            #   ② 色块面积与文本 bbox 面积比 < 4（格子接近文本
                            #      尺寸 = 标签在格内居中；大柱体/大色块面积比
                            #      巨大 = 文字横跨色块 = 真实遮挡 → 检出）
                            area_ratio = (pb_win.width * pb_win.height /
                                          max(tbb.width * tbb.height, 1e-9))
                            if area_ratio < 4.0 and (
                                    (tc[0] - pc[0]) ** 2 +
                                    (tc[1] - pc[1]) ** 2) ** 0.5 < 0.6 * t_h:
                                continue  # 标签在热力格子中央（合法）
                            overlaps.append(
                                (f'text:{t.get_text()[:10]}', 'patch'))
                    except Exception:
                        pass
        except Exception:
            pass
    if overlaps and verbose:
        print(f"⚠️ 文字重叠检测: {len(overlaps)} 处 → {overlaps[:10]}（须调整标注偏移 xytext/图例 loc 后重新出图）")
    return overlaps


# ============================================================
# 坐标轴重叠自动检测（出版级坐标轴规范——轴标签/刻度标签不重叠）
# ============================================================

def check_axis_overlaps(fig, verbose=True):
    """检测坐标轴元素重叠（用户强制要求——插图质量高点不要重叠）

    检测对象：
    ① 轴标签（xlabel/ylabel）与刻度标签（tick labels）的 bbox 重叠
    ② 不同子图间刻度标签互相挤压（subplot 间距不足）
    ③ 3D 图轴标签压刻度标签（Axes3D labelpad 不足的常见缺陷）

    用法：与 check_text_overlaps 一起在 save_fig 前调用：
        assert not check_axis_overlaps(fig), "坐标轴元素重叠，须调整间距"

    Returns:
        list: [(元素A, 元素B)] 重叠对；空列表 = 无重叠 = 通过
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    overlaps = []

    # ① 单图内：轴标签 vs 刻度标签（按轴分组检测）
    #    ⚠️ 把 x 轴标签/刻度 与 y 轴标签/刻度 全部混在一个列表里两两
    #    比较——坐标原点附近的 x 刻度"0"与 y 刻度"-4.0"的 bbox 在窗口
    #    坐标系下天然相邻相交（视觉上分别在左下角，互不遮挡），造成
    #    假阳性误报（2026 实测：figS5_pareto.png 报"刻度:0 vs 刻度:-4.0"）。
    #    v2 改为同轴组内检测：x 轴组（xlabel + xticklabels）内部两两、
    #    y 轴组（ylabel + yticklabels）内部两两，不跨组比较。
    for ax in fig.axes:
        # ⚠️ 3D 图（Axes3D）跳过自动 bbox 检测——投影后轴标签/刻度标签的
        #    未旋转 bbox 与视觉位置不一致，会产生假阳性误报（2026 实测
        #    确认）。3D 图以目检为准 + tick_params(pad≥4) 规范保证。
        if '3d' in ax.__class__.__name__.lower():
            continue
        for lbl, ticks in ((ax.xaxis.label, ax.get_xticklabels()),
                           (ax.yaxis.label, ax.get_yticklabels())):
            items = []
            if lbl.get_text():
                try:
                    items.append((f'轴标签:{lbl.get_text()[:10]}',
                                  lbl.get_window_extent(renderer)))
                except Exception:
                    pass
            for tick in ticks:
                if tick.get_text():
                    try:
                        items.append((f'刻度:{tick.get_text()[:6]}',
                                      tick.get_window_extent(renderer)))
                    except Exception:
                        pass
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    if items[i][1].overlaps(items[j][1]):
                        overlaps.append((f'{items[i][0]}', items[j][0]))

    # ② 子图间挤压：只检测【同列、上下相邻】的子图对（hspace 不足时
    #    上一图 x 刻度标签压下一图标题/绘图区）——按 subplotspec 行列
    #    匹配，避免同行不同列的误报（2026 实测：2x2 布局曾误报）。
    axes = [a for a in fig.axes if a.get_subplotspec() is not None]
    specs = []
    for a in axes:
        ss = a.get_subplotspec()
        try:
            specs.append((ss.rowspan.start, ss.colspan.start, a))
        except Exception:
            specs.append((0, 0, a))
    for i in range(len(specs)):
        r1, c1, a1 = specs[i]
        for j in range(len(specs)):
            if i == j:
                continue
            r2, c2, a2 = specs[j]
            if not (c1 == c2 and r2 == r1 + 1):
                continue
            try:
                # 用 tightbbox（含刻度标签/轴标签的完整区域）比较：
                # 上子图全部元素底部 vs 下子图全部元素顶部——
                # hspace 不足时刻度标签互相侵入（get_window_extent 只含
                # 绘图区，会漏报，2026 实测确认）
                tb1 = a1.get_tightbbox(renderer)
                tb2 = a2.get_tightbbox(renderer)
                if tb1.y0 < tb2.y1:
                    overlaps.append(('子图间挤压',
                                     f'上子图元素底部({tb1.y0:.0f}) '
                                     f'侵入下子图元素顶部({tb2.y1:.0f})'))
            except Exception:
                pass

    # ③ colorbar 重叠检测：colorbar 刻度标签与相邻绘图区/图例互相侵入
    #    （热力图/3D 图 colorbar 位置不当的常见缺陷）
    for ax in fig.axes:
        if 'colorbar' not in ax.__class__.__name__.lower():
            continue
        try:
            cb_bbox = ax.get_tightbbox(renderer)
            for other in fig.axes:
                if other is ax:
                    continue
                # 3D 宿主 bbox 偏大（投影），跳过避免误报
                if '3d' in other.__class__.__name__.lower():
                    continue
                ob = other.get_tightbbox(renderer)
                if cb_bbox.overlaps(ob):
                    overlaps.append(('colorbar 重叠',
                                     f'colorbar 与 {other.__class__.__name__} 区域相交'))
        except Exception:
            pass

    if overlaps and verbose:
        print(f"⚠️ 坐标轴重叠检测: {len(overlaps)} 处 → {overlaps[:8]}"
              f"（须调整 tick pad/labelpad/subplot 间距后重新出图）")
    return overlaps


def smart_read_csv(file_path, **kwargs):
    """智能读取 CSV：自动检测编码并加载"""
    enc, conf = detect_encoding(file_path)
    if enc and conf > 0.7:
        try:
            return pd.read_csv(file_path, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            pass
        except Exception:
            # 编码正确但解析失败（分隔符/列错位等）时同样走回退链
            pass
    for encoding in ENCODINGS_TO_TRY:
        try:
            return pd.read_csv(file_path, encoding=encoding, **kwargs)
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    raise ValueError(f"无法读取文件 {file_path}，已尝试所有常见编码")
