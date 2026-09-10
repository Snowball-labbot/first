# -*- coding: utf-8 -*-
"""
draw_c_figs —— 用真实附件数据 + 顶刊配色，生成 C 题论文核心图表

用法：
    python draw_c_figs.py

产出（figures/）：
    00_配色总览            全部色板 + C 题语义色卡
    01_问题1_单日全景      电价阶梯 + 负载/光伏 + 净负载（问题 1 直接可用）
    02_全年负载热力图      365 天 × 144 时段（附件 2）
    03_全年光伏热力图      365 天 × 144 时段（附件 2）
    04_四季典型日          3.20 / 6.21 / 9.23 / 12.21（题目指定日期）
    05_全年电价热力图      波动电价（附件 4，问题 4）
    06_光伏预报vs实际      附件 3 预报 vs 附件 2 实际（问题 3）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from mgstyle import (PALETTES, C, LINE, CMAP, set_style, style_axes,
                     newfig, savefig, show_palettes)

ATT = HERE / "附件"
FIG = HERE / "figures"

DATES_SHOW = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
SEASON_CN = ["春分 3.20", "夏至 6.21", "秋分 9.23", "冬至 12.21"]


# ---------------------------------------------------------------- 数据
def load_all():
    d = {}
    a1 = pd.read_excel(ATT / "附件1.xlsx")
    d["a1"] = a1
    a2_load = pd.read_excel(ATT / "附件2.xlsx", sheet_name="小区负载")
    a2_pv = pd.read_excel(ATT / "附件2.xlsx", sheet_name="光伏发电实际功率")
    d["a2_load"], d["a2_pv"] = a2_load, a2_pv
    d["a3"] = pd.read_excel(ATT / "附件3.xlsx")
    d["a4"] = pd.read_excel(ATT / "附件4.xlsx")
    return d


def to_hours(times):
    """time 对象序列 → 小时（浮点）"""
    return np.array([t.hour + t.minute / 60 + t.second / 3600 for t in times])


def hours_from_col(col):
    """附件时间列 → 小时（浮点）。
    坑：列是混合类型——大部分是 time 对象，但 "0:00+1"（次日零点）是字符串。
    "+1" 按 +24h 处理，正好得到 0:10 ... 24:00 的连续横轴。
    """
    out = []
    for v in col:
        if isinstance(v, str):
            plus = "+1" in v
            s = v.replace("+1", "").strip()
            t = pd.to_datetime(s).time()
            h = t.hour + t.minute / 60 + t.second / 3600
            out.append(h + 24 if plus else h)
        else:
            out.append(v.hour + v.minute / 60 + v.second / 3600)
    return np.array(out)


def wide_to_matrix(df: pd.DataFrame):
    """附件2/4 宽表 → (日期列表, 时间小时数组, 365×144 数值矩阵)"""
    times = list(df.columns[1:])
    hours = hours_from_col(times)
    dates = pd.to_datetime(df.iloc[:, 0].astype(str).str.replace("/", "-"))
    mat = df.iloc[:, 1:].to_numpy(dtype=float)
    order = np.argsort(hours)
    return dates.values, hours[order], mat[:, order]


# ---------------------------------------------------------------- 图
def fig1_single_day(d):
    """问题 1 单日全景：上=负载/光伏，中=净负载，下=电价"""
    a1 = d["a1"]
    h = hours_from_col(a1["时间"])
    price, load, pv = (a1["电价"].values, a1["小区负载"].values,
                       a1["光伏发电预测功率"].values)

    fig, axes = newfig((9.2, 7.6), nrows=3, ncols=1, sharex=True,
                       gridspec_kw={"height_ratios": [2.2, 1.3, 1.3]})

    # (a) 负载与光伏
    ax = axes[0]
    ax.fill_between(h, pv, color=C["光伏"], alpha=.45, lw=0, label="光伏发电预测功率")
    ax.plot(h, pv, color=LINE["光伏"], lw=1.4)
    ax.plot(h, load, color=LINE["负载"], lw=1.8, label="小区负载")
    style_axes(ax, "", "功率 (kW)", "(a) 小区负载与光伏出力", legend=True, fs=10)
    ax.set_xlim(0, 24); ax.set_xticks(range(0, 25, 4))

    # (b) 净负载（负载-光伏）：>0 需购电/放电，<0 可充电/弃电
    ax = axes[1]
    net = load - pv
    ax.axhline(0, color=C["参考"], lw=.9)
    ax.fill_between(h, net, 0, where=net >= 0, color=C["紧急"], alpha=.30, lw=0,
                    label="缺口（需购电/放电）")
    ax.fill_between(h, net, 0, where=net < 0, color=C["充电"], alpha=.35, lw=0,
                    label="盈余（可充电）")
    ax.plot(h, net, color=LINE["负载"], lw=1.3)
    style_axes(ax, "", "功率 (kW)", "(b) 净负载 = 负载 − 光伏", legend=True, fs=10)
    ax.set_xlim(0, 24)

    # (c) 电价阶梯
    ax = axes[2]
    ax.step(h, price, where="post", color=C["电价"], lw=1.8)
    ax.fill_between(h, price, step="post", color=C["电价"], alpha=.18, lw=0)
    style_axes(ax, "时刻 (h)", "电价 (元/kWh)", "(c) 分时电价", legend=False, fs=10)
    ax.set_xlim(0, 24)

    fig.align_ylabels(axes)
    fig.tight_layout()
    return savefig(fig, "01_问题1_单日全景", outdir=FIG)


def fig2_heatmap(d):
    """全年负载 / 光伏 日历热力图"""
    dates_l, hours_l, mat_l = wide_to_matrix(d["a2_load"])
    dates_p, hours_p, mat_p = wide_to_matrix(d["a2_pv"])

    fig, axes = newfig((9.6, 6.4), nrows=2, ncols=1)
    for ax, mat, cm, ttl in (
            (axes[0], mat_l, CMAP["load"], "(a) 全年小区负载 (kW)"),
            (axes[1], mat_p, CMAP["pv"], "(b) 全年光伏实际出力 (kW)")):
        im = ax.imshow(mat, aspect="auto", cmap=cm, interpolation="nearest",
                       extent=[hours_l[0], hours_l[-1], 365, 0])
        ax.set_yticks([1, 60, 121, 182, 243, 304, 364])
        ax.set_yticklabels(["1月", "3月", "5月", "7月", "9月", "11月", "12月"])
        ax.set_xticks(range(0, 25, 4))
        ax.grid(False)
        ax.set_title(ttl, pad=8, fontweight="bold", fontsize=11)
        cb = fig.colorbar(im, ax=ax, shrink=.92, pad=.012)
        cb.outline.set_visible(False)
        cb.ax.tick_params(labelsize=8.5)
    axes[1].set_xlabel("时刻 (h)")
    fig.tight_layout()
    return savefig(fig, "02_全年负载与光伏热力图", outdir=FIG)


def fig3_seasons(d):
    """四季典型日：题目指定日期的负载与光伏"""
    dates_l, hours_l, mat_l = wide_to_matrix(d["a2_load"])
    dates_p, hours_p, mat_p = wide_to_matrix(d["a2_pv"])
    dl = pd.to_datetime(dates_l)

    fig, axes = newfig((9.6, 7.4), nrows=2, ncols=1, sharex=True)
    for i, (ds, cn) in enumerate(zip(DATES_SHOW, SEASON_CN)):
        day = pd.Timestamp(ds)
        j = int(np.argmin(np.abs(dl - day)))
        axes[0].plot(hours_l, mat_l[j], lw=1.7, color=PALETTES["zhihu4_pnas"][i],
                     label=f"{cn}  负载")
        axes[1].plot(hours_p, mat_p[j], lw=1.7, color=PALETTES["zhihu4_pnas"][i],
                     label=f"{cn}  光伏")
    style_axes(axes[0], "", "功率 (kW)", "(a) 小区负载（四个典型日）", fs=10)
    style_axes(axes[1], "时刻 (h)", "功率 (kW)", "(b) 光伏实际出力（四个典型日）", fs=10)
    for ax in axes:
        ax.set_xlim(0, 24); ax.set_xticks(range(0, 25, 4))
    fig.tight_layout()
    return savefig(fig, "03_四季典型日对比", outdir=FIG)


def fig4_price(d):
    """电价：附件 1 固定分时电价 + 附件 4 全年波动电价热力图"""
    a1 = d["a1"]
    h = hours_from_col(a1["时间"])
    dates4, hours4, mat4 = wide_to_matrix(d["a4"])

    fig, axes = newfig((9.6, 6.8), nrows=2, ncols=1,
                       gridspec_kw={"height_ratios": [1, 1.5]})
    ax = axes[0]
    ax.step(h, a1["电价"].values, where="post", color=C["电价"], lw=2)
    ax.fill_between(h, a1["电价"].values, step="post", color=C["电价"], alpha=.15, lw=0)
    style_axes(ax, "", "电价 (元/kWh)", "(a) 固定分时电价（附件 1）", legend=False, fs=10)
    ax.set_xlim(0, 24)

    ax = axes[1]
    im = ax.imshow(mat4, aspect="auto", cmap=CMAP["price"], interpolation="nearest",
                   extent=[hours4[0], hours4[-1], 365, 0])
    ax.set_yticks([1, 60, 121, 182, 243, 304, 364])
    ax.set_yticklabels(["1月", "3月", "5月", "7月", "9月", "11月", "12月"])
    ax.set_xticks(range(0, 25, 4))
    ax.grid(False)
    ax.set_title("(b) 全年波动电价 (元/kWh，附件 4)", pad=8, fontweight="bold", fontsize=11)
    ax.set_xlabel("时刻 (h)")
    cb = fig.colorbar(im, ax=ax, shrink=.92, pad=.012)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8.5)
    fig.tight_layout()
    return savefig(fig, "04_电价_固定与波动", outdir=FIG)


def fig5_forecast(d):
    """光伏预报 vs 实际：某日 0:00 发布的 24h 预报 vs 实际出力"""
    a3 = d["a3"].copy()
    a3["日期"] = a3["日期"].ffill()
    a3["日期dt"] = pd.to_datetime(a3["日期"].astype(str).str.replace("/", "-"))
    target = pd.Timestamp(DATES_SHOW[1])          # 6.21 夏至
    row = a3[(a3["日期dt"] == target) & (a3["预报时刻"].astype(str).str.startswith("0"))]
    if row.empty:
        row = a3[a3["日期dt"] == target].head(1)
    fcols = [c for c in a3.columns if re.fullmatch(r"预报\d+小时", str(c))]
    fvals = row.iloc[0][fcols].to_numpy(float)
    fh = np.arange(1, len(fvals) + 1)             # 预报 k 小时 → 目标日 k 点

    dates_p, hours_p, mat_p = wide_to_matrix(d["a2_pv"])
    dp = pd.to_datetime(dates_p)
    j = int(np.argmin(np.abs(dp - target)))
    actual, ah = mat_p[j], hours_p

    fig, ax = newfig((8.8, 4.6))
    ax.plot(ah, actual, color=C["实际"], lw=2.0, label="实际出力（附件 2）")
    ax.fill_between(ah, actual, color=C["实际"], alpha=.10, lw=0)
    ax.plot(fh, fvals, color=C["计划"], lw=1.9, ls="--", marker="o", ms=4.5,
            label="0:00 发布的 24h 预报（附件 3）")
    style_axes(ax, "时刻 (h)", "功率 (kW)",
               f"{target:%Y-%m-%d} 光伏预报与实际对比", legend=True, fs=10)
    ax.set_xlim(0, 24); ax.set_xticks(range(0, 25, 4))
    fig.tight_layout()
    return savefig(fig, "06_光伏预报vs实际", outdir=FIG)


def main():
    cn = set_style(font_size=10.5)
    print("中文字体:", cn or "未找到！")
    print("数据读取中 ...")
    d = load_all()

    print("图 0/6 配色总览")
    show_palettes(outdir=FIG)
    print("图 1/6 问题1 单日全景")
    fig1_single_day(d)
    print("图 2/6 全年热力图")
    fig2_heatmap(d)
    print("图 3/6 四季典型日")
    fig3_seasons(d)
    print("图 4/6 电价")
    fig4_price(d)
    print("图 5/6 预报 vs 实际")
    fig5_forecast(d)
    print("\n全部完成 → figures/")


if __name__ == "__main__":
    main()
