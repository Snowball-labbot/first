# -*- coding: utf-8 -*-
"""数学建模求解公共头部 —— 求解脚本统一 import 本文件。

用法（在 求解/问题X/ 下的求解脚本中）：
    import sys, os
    sys.path.insert(0, r"<math-modeling技能目录>/scripts")  # 或把本文件复制到 求解/ 目录
    from common import *                                   # noqa

提供：Agg 后端、中文字体回退链、学术配色 COLORS、图幅常量、
save_fig/save_csv（自动落到当前脚本所在目录的 图片/ 与 结果/）、
despine、print_stats、智能编码读取 read_table_auto。
"""
import os
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---- 中文字体回退链（Windows / macOS / Linux 通吃）----
_CJK_FONTS = [
    "SimHei", "Microsoft YaHei", "PingFang SC", "Heiti TC", "STHeiti",
    "Hiragino Sans GB", "Noto Sans CJK SC", "Source Han Sans CN",
    "WenQuanYi Micro Hei", "Arial Unicode MS", "DejaVu Sans",
]
plt.rcParams["font.sans-serif"] = _CJK_FONTS
plt.rcParams["axes.unicode_minus"] = False   # 中文负号乱码防护
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 300            # 论文用 300 DPI
plt.rcParams["savefig.bbox"] = "tight"

# ---- 学术配色（灰度打印可区分；与 MathModelAgent 配色体系一致）----
COLORS = {
    "primary": "#2E5B88",   # 蓝
    "accent": "#E85D4C",    # 红橙
    "positive": "#4A9B7F",  # 绿
    "neutral": "#7F7F7F",   # 灰
    "light": "#B8D4E8",     # 浅蓝
}
DEFAULT_COLORS = ["#2E5B88", "#E85D4C", "#4A9B7F", "#7F7F7F", "#B8D4E8"]

# ---- 图幅常量 ----
FIG_SINGLE = (5, 4)
FIG_DOUBLE = (10, 4)
FIG_WIDE = (8, 3)
FIG_SQUARE = (6, 6)


def _caller_dir():
    """当前运行脚本所在目录（save_fig/save_csv 的落盘基准）。"""
    argv0 = sys.argv[0] if sys.argv and sys.argv[0] else ""
    if argv0 and os.path.isfile(argv0):
        return os.path.dirname(os.path.abspath(argv0))
    return os.getcwd()


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def _pic_dir():
    return _ensure_dir(os.path.join(_caller_dir(), "图片"))


def _out_dir():
    return _ensure_dir(os.path.join(_caller_dir(), "结果"))


def save_fig(fig, name_cn, out_dir=None):
    """保存图片（300 DPI PNG，文件名中文），并关闭 figure。

    图内不要画 set_title——论文标题由 \\caption{} 承担。
    """
    d = out_dir or _pic_dir()
    path = os.path.join(d, name_cn if name_cn.endswith(".png") else name_cn + ".png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[save_fig] {path}")
    return path


def save_csv(df, name_cn, out_dir=None):
    """保存结果表（utf-8-sig，Excel 直接打开不乱码）。"""
    d = out_dir or _out_dir()
    path = os.path.join(d, name_cn if name_cn.endswith(".csv") else name_cn + ".csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[save_csv] {path}")
    return path


def despine(ax):
    """隐藏上、右边框（学术图惯例）。"""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return ax


def print_stats(data, name=""):
    """打印 min/max/mean/std/CV/amplitude —— 论文可直接引用的一组统计量。"""
    arr = np.asarray(data, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        print(f"[stats] {name}: 无有效数值")
        return
    mean, std = arr.mean(), arr.std(ddof=1) if arr.size > 1 else 0.0
    cv = std / mean if mean != 0 else float("inf")
    print(
        f"[stats] {name}  n={arr.size}  min={arr.min():.4g}  max={arr.max():.4g}  "
        f"mean={mean:.4g}  std={std:.4g}  CV={cv:.4g}  amplitude={arr.max() - arr.min():.4g}"
    )


def read_table_auto(path, **kwargs):
    """智能编码读取表格：utf-8 → gbk → gb2312 → latin-1；支持 csv/xlsx/xls。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=None, **kwargs)  # 返回 {sheet: df}，由调用方选择
    if ext == ".csv":
        for enc in ("utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"):
            try:
                return pd.read_csv(path, encoding=enc, **kwargs)
            except (UnicodeDecodeError, UnicodeError):
                continue
    raise ValueError(f"无法读取 {path}")


if __name__ == "__main__":
    # 自测：生成一张图、一张表、一组统计量
    x = np.linspace(0, 2 * np.pi, 100)
    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    ax.plot(x, np.sin(x), color=COLORS["primary"], lw=1.5, marker="o", ms=3, label="sin")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.grid(alpha=0.3, linestyle="--")
    ax.legend(frameon=False)
    despine(ax)
    save_fig(fig, "自测_正弦曲线")
    save_csv(pd.DataFrame({"x": x, "sin": np.sin(x)}), "自测_数据.csv")
    print_stats(np.sin(x), "自测序列")
    print("common.py 自测通过")
