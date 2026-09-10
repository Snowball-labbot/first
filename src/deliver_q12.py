"""Build the Q1/Q2 manuscript, plotting inputs, figures and Excel payload.

This never refits forecasts or changes dispatch decisions. Inputs are saved results.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from src.q12 import B, TOL, audit_trace, dump_json, interval_label, optimize_day


LABELS = {"seasonal_q0":"同期预测 无余量", "ridge_q0":"岭回归 无余量",
          "seasonal_q0.7":"同期预测 70%余量", "ridge_q0.7":"岭回归 70%余量"}
COLORS = {"load":"#3E608D", "pv":"#E8A33D", "pv_fill":"#F0C284", "grid":"#4D779B",
          "soc":"#8074C8", "emergency":"#992224", "forecast":"#7895C1", "actual":"#CD3B42", "base":"#9D9EA3"}
DATES = ["2025-03-20","2025-06-21","2025-09-23","2025-12-21"]


def md_table(headers, rows):
    def fmt(x):
        return f"{x:,.2f}" if isinstance(x,(float,np.floating)) else str(x)
    return "\n".join(["| "+" | ".join(headers)+" |", "| "+" | ".join(["---"]*len(headers))+" |"]+
                     ["| "+" | ".join(fmt(x) for x in r)+" |" for r in rows])


def blocks(f):
    return [[f"{h:02d}:00-{h+4:02d}:00",float(f.iloc[h*6:(h+4)*6].charge_kwh.sum()),
             float(f.iloc[h*6:(h+4)*6].discharge_kwh.sum())] for h in range(0,24,4)]


def emergency_runs(f):
    positive = f.emergency_kwh.to_numpy()>TOL
    result=[];i=0
    while i<len(f):
        if not positive[i]:
            i+=1;continue
        j=i+1
        while j<len(f) and positive[j]:j+=1
        label=interval_label(i).split("-")[0]+"-"+interval_label(j-1).split("-")[1]
        result.append([label,float(f.emergency_kwh.iloc[i:j].sum())]);i=j
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=Path("artifacts/q12"))
    parser.add_argument("--skill-root",type=Path,default=Path.home()/".codex/skills/math-modeling")
    args=parser.parse_args();out=args.out
    sys.path.insert(0,str(args.skill_root/"tools/figure/scripts"))
    from export_figure import export_figure
    from visual_qa import audit_layout
    q1=pd.read_csv(out/"q1_intervals.csv")
    a=json.loads((out/"q1_summary.json").read_text(encoding="utf-8"))
    summary=json.loads((out/"q2_summary.json").read_text(encoding="utf-8"))
    manifest=json.loads((out/"run_manifest.json").read_text(encoding="utf-8"))
    if manifest["stage"]!="full":raise ValueError("Full-year outputs required")
    selected=summary["selected_strategy"]
    f=pd.read_csv(out/f"{selected}_intervals.csv.gz")
    f["interval_start"]=pd.to_datetime(f.interval_start)
    daily=pd.read_csv(out/"q2_daily_metrics.csv")
    chosen_daily=daily[daily.strategy==selected].set_index("date")
    val=pd.read_csv(out/"policy_validation.csv")
    metrics={r["strategy"]:r for r in summary["strategies"]}
    m=metrics[selected];base=metrics["seasonal_q0"];r0=metrics["ridge_q0"]
    audit={"q1":audit_trace(q1,initial=6000),"q2":{},"accounting":{}}
    for name,row in metrics.items():
        trace=pd.read_csv(out/f"{name}_intervals.csv.gz")
        audit["q2"][name]=audit_trace(trace,initial=manifest["evaluation_initial_soc"])
        cost=float(np.dot(trace.plan_kwh+5*trace.emergency_kwh,trace.price))
        if abs(cost-row["total_cost_yuan"])>0.02:raise AssertionError("Saved trace accounting differs")
        audit["accounting"][name]={"recomputed_cost_yuan":cost,"difference_yuan":cost-row["total_cost_yuan"]}
        if len(trace)!=334*144:raise AssertionError("Incomplete trace")
    dump_json(out/"saved_output_audit.json",audit)
    f[f.date.isin(DATES)].to_csv(out/"selected_dates_plot_data.csv",index=False)
    q1_sensitivity=[]
    for eta in (0.9,float(np.sqrt(0.9))):
        _,meta=optimize_day(q1.load_kwh.to_numpy(),q1.pv_kwh.to_numpy(),q1.price.to_numpy(),6000,(6000,"equal"),
                          battery=replace(B,eta_c=eta,eta_d=eta))
        q1_sensitivity.append({"eta_charge":eta,"eta_discharge":eta,"round_trip":eta**2,"cost_yuan":meta["cost"]})
    pd.DataFrame(q1_sensitivity).to_csv(out/"q1_efficiency_sensitivity.csv",index=False)
    payload={"q1":{"plan":[[interval_label(i),float(g)] for i,g in enumerate(q1.plan_kwh)],
                    "storage":[r+(["00:00",6000] if i==0 else ["24:00",6000] if i==1 else [None,None])
                               for i,r in enumerate(blocks(q1))]},
             "q2":{"headers":["日期\\时间"]+[interval_label(i) for i in range(144)]+["全天购电量","全天购电费"],
                    "plan":[],"storage":[],"emergency":[]}}
    for date,g in f.groupby("date",sort=True):
        s=chosen_daily.loc[date]
        payload["q2"]["plan"].append([date]+g.plan_kwh.astype(float).tolist()+[float(s.plan_kwh),float(s.total_cost_yuan)])
        for i,row in enumerate(blocks(g)):
            payload["q2"]["storage"].append([date if i==0 else None]+row+
                (["00:00",float(s.soc_start_kwh)] if i==0 else ["24:00",float(s.soc_end_kwh)] if i==1 else [None,None]))
        runs=emergency_runs(g)
        if not runs:runs=[["无紧急购电",0.0]]
        payload["q2"]["emergency"].extend([[date if i==0 else None]+row for i,row in enumerate(runs)])
    dump_json(out/"xlsx_payload.json",payload)
    pd.DataFrame({"slot":np.arange(144),"input_right_endpoint":[interval_label(i).split("-")[1] for i in range(144)],
                  "normalized_output_interval":[interval_label(i) for i in range(144)]}).to_csv(out/"time_mapping.csv",index=False)
    figdir=Path("figures/q12");figdir.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei","SimHei","DejaVu Sans"],"axes.unicode_minus":False,
                         "font.size":10,"axes.spines.top":False,"axes.spines.right":False,"svg.fonttype":"none"})
    figure_audit={}
    def save(fig,name):
        issues=audit_layout(fig)
        if any(level in ("FAIL","WARN") for level,_ in issues):raise RuntimeError(f"Figure layout: {issues}")
        figure_audit[name]=issues
        export_figure(fig,str(figdir/name),formats=["png","svg"],dpi=300,size_inches=tuple(fig.get_size_inches()),
                      grayscale_preview=False,tight=False)
        svg=figdir/(name+".svg")
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())+"\n",
                       encoding="utf-8",newline="\n")
        plt.close(fig)
    x=(np.arange(144)+0.5)/6
    fig,axs=plt.subplots(2,1,figsize=(7.2,5.8),sharex=True,layout="constrained",gridspec_kw={"height_ratios":[2,1]})
    for key,label,color in [("load_kwh","负载",COLORS["load"]),("pv_kwh","光伏",COLORS["pv"]),("plan_kwh","计划购电",COLORS["grid"])]:
        axs[0].plot(x,q1[key]*6,label=label,color=color,lw=1.5,ls="--" if key=="plan_kwh" else "-")
    axs[0].set_ylim(0,1.25*q1[["load_kwh","pv_kwh","plan_kwh"]].to_numpy().max()*6)
    axs[0].set_ylabel("功率 / kW");axs[0].legend(ncol=3,loc="upper left");axs[0].set_title("(a) 单日供需与购电",loc="left",fontsize=11)
    axs[1].plot(np.arange(145)/6,np.r_[q1.soc_start_kwh.iloc[0],q1.soc_end_kwh],color=COLORS["soc"])
    axs[1].axhline(1200,color=COLORS["base"],ls=":");axs[1].axhline(10800,color=COLORS["base"],ls=":")
    axs[1].set_ylabel("储电量 / kWh");axs[1].set_xlabel("时刻 / h");axs[1].set_xticks(np.arange(0,25,4));axs[1].set_xlim(0,24)
    axs[1].set_title("(b) 储能状态",loc="left",fontsize=11);save(fig,"q1_dispatch")
    fig,axs=plt.subplots(2,1,figsize=(7.2,5.4),sharex=True,layout="constrained")
    g=f[f.date==DATES[0]]
    for ax,key,label in zip(axs,("load","pv"),("负载","光伏")):
        ax.plot(x,g[key+"_kwh"]*6,color=COLORS["actual"],label="实际值",lw=1.4)
        ax.plot(x,g["forecast_"+key+"_kwh"]*6,color=COLORS["forecast"],label="日前预测",ls="--",lw=1.5)
        ax.set_ylabel(label+" / kW");ax.set_ylim(0,1.25*g[[key+"_kwh","forecast_"+key+"_kwh"]].to_numpy().max()*6)
    axs[0].legend(ncol=2,loc="upper left");axs[0].set_title("2025-03-20 岭回归日前预测",loc="left",fontsize=11)
    axs[1].set_xlabel("时刻 / h");axs[1].set_xticks(np.arange(0,25,4));axs[1].set_xlim(0,24);save(fig,"q2_forecast")
    names=list(metrics);idx=np.arange(len(names))
    fig,ax=plt.subplots(figsize=(7.2,4.5),layout="constrained")
    normal=np.array([metrics[n]["normal_cost_yuan"] for n in names])/1e4
    emerg=np.array([metrics[n]["emergency_cost_yuan"] for n in names])/1e4
    ax.bar(idx,normal,color=COLORS["grid"],label="计划购电费",width=.55)
    ax.bar(idx,emerg,bottom=normal,color=COLORS["emergency"],label="紧急购电费",width=.55)
    ax.set_xticks(idx,[LABELS[n].replace(" ","\n") for n in names]);ax.set_ylabel("2—12月费用 / 万元")
    ax.set_ylim(0,max(normal+emerg)*1.23);ax.legend(ncol=2,loc="upper right")
    for i,total in enumerate(normal+emerg):ax.text(i,total+20,f"{total:,.1f}",ha="center",fontsize=10)
    save(fig,"q2_cost_comparison")
    fig,axs=plt.subplots(1,2,figsize=(7.2,3.5),layout="constrained")
    for method,color in [("seasonal",COLORS["base"]),("ridge",COLORS["load"])]:
        v=val[val.forecast==method]
        label="同期预测" if method=="seasonal" else "岭回归"
        axs[0].plot(range(4),v.cost_yuan/1e4,color=color,marker="o",ms=4,label=label)
        axs[1].plot(range(4),v.emergency_cost_yuan/1e4,color=color,marker="s",ms=4,label=label)
    for ax in axs:
        ax.set_xticks(range(4),["无余量","70%","80%","90%"]);ax.set_xlabel("历史误差分位数");ax.set_ylim(bottom=0)
    axs[0].set_ylabel("验证期总费用 / 万元");axs[1].set_ylabel("验证期紧急费用 / 万元")
    axs[0].legend(loc="lower left",fontsize=9);save(fig,"q2_validation")
    dump_json(out/"figure_layout_audit.json",figure_audit)
    q1table=md_table(["时段","计划购电量 / kWh"],[[interval_label(h*6),float(q1.plan_kwh.iloc[h*6])] for h in (10,12,14,16,18,20)])
    q1storage=md_table(["时段","充电量 / kWh","放电量 / kWh"],blocks(q1))
    comparison=md_table(["策略","计划费 / 万元","紧急费 / 万元","总费用 / 万元","紧急购电 / kWh"],
                        [[LABELS[n],metrics[n]["normal_cost_yuan"]/1e4,metrics[n]["emergency_cost_yuan"]/1e4,
                          metrics[n]["total_cost_yuan"]/1e4,metrics[n]["emergency_kwh"]] for n in names])
    forecast_table=md_table(["预测器","负载 MAE / kW","负载 RMSE / kW","光伏 MAE / kW","光伏 RMSE / kW"],
                            [["同期预测",base["load_mae_kw"],base["load_rmse_kw"],base["pv_mae_kw"],base["pv_rmse_kw"]],
                             ["岭回归",m["load_mae_kw"],m["load_rmse_kw"],m["pv_mae_kw"],m["pv_rmse_kw"]]])
    date_summary=md_table(["日期","全天计划购电 / kWh","全天总购电费 / 元","紧急购电 / kWh","日初 SOC / kWh","日末 SOC / kWh"],
                           [[d,*[float(chosen_daily.loc[d,k]) for k in ["plan_kwh","total_cost_yuan","emergency_kwh","soc_start_kwh","soc_end_kwh"]]] for d in DATES])
    # Build text from computed evidence. Mathematics stays editable in Markdown.
    text=rf'''# 考虑预测误差的微网日前购电与储能调度

第一问与第二问初稿

## 摘要

针对小区光伏发电、负载需求与分时电价共同影响的微网购电问题，建立统一的能量平衡与储能状态模型。在给定单日曲线时，以计划购电费最小为目标，采用混合整数线性规划约束充放电互斥，并要求日初日末储电量相等。对于未来供需未知的情形，比较同期预测和岭回归，使用历史净负载误差的分位数构造非负余量，再通过实际运行仿真评估计划费用与五倍电价的紧急购电费用。

在充电、放电效率分别为 90%，输入功率视为十分钟区间平均值的假设下，第一问全天计划购电 {a['plan_kwh']:,.2f} kWh，购电费 {a['cost']:,.2f} 元，相对无储能基线降低 {a['saving_percent']:.2f}%。第二问利用一月份验证数据选择岭回归与 70% 分位数余量，随后在 2—12 月 334 天进行顺序回测。该策略总费用为 {m['total_cost_yuan']/1e4:,.2f} 万元，相对同期预测无余量基线下降 {100*(1-m['total_cost_yuan']/base['total_cost_yuan']):.2f}%；相对岭回归无余量策略下降 {100*(1-m['total_cost_yuan']/r0['total_cost_yuan']):.2f}%。结果表明，预测改进与适量风险余量均能降低费用，但更高余量虽可进一步减少紧急购电，也可能增加总成本。本稿仅回答前两问，其结论限于所列信息、时间、效率与运行假设。

关键词：微网调度；混合整数线性规划；岭回归；风险余量；时间顺序回测

## 1 问题分析

题面及附件提供了微网的物理参数、供需曲线与结果模板 [1]。第一问的电价、负载和光伏预测曲线已给定，需决定各时段的购电与储能安排，属于确定性优化问题，不需要拟合预测模型。储能的经济作用来自跨时段转移电量，必须同时考虑功率上限、容量边界和能量损失。

第二问要求每天午夜制定整天计划。实际用电和发电变化后，普通购电仍按计划量付费，剩余供电缺口通过五倍电价紧急补购。因此，少买与多买均存在代价。模型分为日前预测、计划优化和实时执行三个部分；历史真实值用于过去信息与事后评价，不能用于提前决定当天购电量。

## 2 数据处理与模型假设

附件 1 含 144 个十分钟时刻，附件 2 的负载与光伏各含 365×144＝52,560 个观测。实际读取未发现缺失值、负数或日期重复，保留全部样本，不对波峰进行无依据的删除或平滑。附件 1 部分时间单元格为字符串、部分为时间类型，读取后统一转换为分钟数，检查为 10、20、…、1440 的完整序列。

采用下列假设，并将它们与题面直接给定的参数区分：

1. 每个功率值表示以其时间标签为右端点的十分钟区间平均功率。电量为功率乘 1/6 小时。模板的区间标签存在疑似错位，本稿按内部区间起止时间汇总，导出副本同步采用规范标签，原始附件保持不变。
2. 充电和放电效率各取 0.9，往返效率为 0.81；功率上限定义在微网母线侧。另检验总往返效率 0.9 的解释。
3. 不设置题面未给出的售电收入，允许无法利用的剩余电量被弃用。计划富余电量仍付费。
4. 实时控制采用每十分钟内功率恒定且可即时平衡的近似。当前区间缺口可以被电池和紧急购电补足；这不是提前知道整天真实曲线。
5. 第二问实际 SOC 跨日连续，日前预测轨迹的日末 SOC 下限取 6000 kWh，作为避免耗空电池的策略设置，不强制实际日末回到此值。评价期初值由统一的一月份因果热身策略得到，不从二月起每天重置。

记区间负载与光伏电量为 $L_t,V_t$，计划购电为 $g_t$，紧急购电为 $e_t$，母线侧充电与放电为 $c_t,d_t$，未利用电量为 $w_t$，区间起点储电量为 $S_t$。上述电量单位均为 kWh，电价 $p_t$ 单位为元/kWh。

## 3 第一问的确定性优化模型

### 3.1 目标与约束

最小化全天购电费用：

$$
\min C_1=\sum_{{t=1}}^{{144}}p_tg_t.
$$

第一问不设置紧急购电，能量平衡与储能状态满足：

$$
g_t+V_t+d_t=L_t+c_t+w_t,\qquad w_t\ge0,
$$

$$
S_{{t+1}}=S_t+0.9c_t-\frac{{d_t}}{{0.9}},\qquad1200\le S_t\le10800.
$$

令 $z_t\in\{{0,1\}}$ 表示充电状态，母线侧每区间最大充放电量为 $M=5000/6$ kWh，规定

$$
0\le c_t\le Mz_t,\qquad0\le d_t\le M(1-z_t),\qquad g_t\ge0.
$$

取 $S_1=S_{{145}}=6000$ kWh。该等式避免利用初始存量净放电制造虚假的节省。模型共有 865 个变量，其中 144 个为二元变量；利用 SciPy 的 MILP 接口调用 HiGHS 求解 [2]。

### 3.2 求解结果

全天计划购电量为 **{a['plan_kwh']:,.2f} kWh**，购电费为 **{a['cost']:,.2f} 元**。无储能基线按正净负载直接购电，费用为 {a['no_storage_cost']:,.2f} 元，采用储能后降低 {a['saving_percent']:.2f}%。表 1 给出题目指定区间，表 2 给出四小时充放电汇总。图 1 展示供需、购电与储能轨迹。

表 1 第一问指定区间计划购电量

{q1table}

表 2 第一问储能运行汇总

{q1storage}

00:00 与 24:00 的储电量均为 6000.00 kWh。充电量记录进入电池前的母线电量，放电量记录电池返回母线的电量，二者不应直接按无损储能作差。

![图1 第一问单日调度与储电量](../figures/q12/q1_dispatch.png)

图 1 第一问单日供需、购电与 SOC 轨迹

### 3.3 结果检验与效率敏感性

整数模型的目标值与 LP 松弛下界之差为 {a['lp_gap_yuan']:.8f} 元，求解器报告相对间隙为 {a['mip_gap']:.2g}。因此，在当前输入与约束口径下，第一问已获得数值精度内的全局最优解。最大能量平衡残差约 {a['audit']['max_balance_residual_kwh']:.2e} kWh，未出现同时充放电。

若“效率 90%”解释为总往返效率，将两侧效率均设为 $\sqrt{{0.9}}$，第一问费用变为 {q1_sensitivity[1]['cost_yuan']:,.2f} 元。由此可见，效率定义会影响数值结论，后续整篇论文应保持同一口径，不混用两组结果。

## 4 第二问的预测与风险余量模型

### 4.1 时间顺序与预测器

以 1 月 22—31 日为验证区间，模型只用各预测时点之前已结束的日期训练。岭回归从积累足够历史后开始，每七天重新拟合一次，最多使用最近 60 天。样本不足时采用简单历史曲线。验证期选择完成后，将规则固定并应用到 2—12 月，后续已观测数据可以进入下一次更新，但不回写历史预测。

同期基线使用昨日和上周同日相同时段的均值。岭回归使用昨日、前日、上周同日的同槽电量，最近三日与七日同槽均值、七日标准差、过去日均值，三阶日内正余弦项以及星期指示变量，共 21 个特征。所有标准化参数均由当前训练段计算，预测当日的真实负载与光伏不进入特征。

对负载和光伏分别拟合带截距的岭回归 [3]：

$$
\min_{{\beta,b}}\sum_i(y_i-b-x_i^T\beta)^2+\lambda\|\beta\|_2^2.
$$

截距不参与惩罚。验证比较 $\lambda\in\{{1,10,100\}}$，两种变量均选择 $\lambda=1$。预测值截断为非负；如果某时槽过去七日的光伏均为零，则其预测置零。该规则只利用历史，但对日出日落变化的适应存在滞后。

### 4.2 风险余量

令净负载预测误差为

$$
\varepsilon_{{d,t}}=(L_{{d,t}}-V_{{d,t}})-(\hat L_{{d,t}}-\hat V_{{d,t}}).
$$

对决策日之前最近 28 天、目标时槽前后三个十分钟槽内的历史误差取经验分位数，并截断为非负，得到余量 $r_{{d,t}}(q)$。不足 28 天时只使用已有历史，时槽池化不跨越日界。初稿比较无余量以及 $q=0.7,0.8,0.9$。

将 $\hat L+r(q)$ 与 $\hat V$ 代入第一问的物理模型，以计划购电费最小求得日前计划，同时将预测轨迹日末储电量约束为至少 6000 kWh。这里的分位数余量是一种可解释的风险控制近似，**不是精确求解全年随机最优控制，也不等于以概率 q 保证全日无缺口**。

### 4.3 实时执行与费用

当天计划确定后不再倒改。每一十分钟区间，令计划购电与实际光伏减去实际负载的差额为 $u_t$。当 $u_t\ge0$ 时，在功率和容量允许范围内充电，剩余部分记为未利用电量；当 $u_t<0$ 时，先按功率和 SOC 限制尽可能放电，剩余缺口记为紧急购电。所有区间均满足供电平衡，实际 SOC 连续传递至次日。

实际评价费用为

$$
C_2=\sum_tp_tg_t^{{plan}}+\sum_t5p_te_t.
$$

普通购电按计划量收费，未利用的计划电量不退款。余量参数按验证期的该项总费用选择，而不是只按预测误差或紧急购电量选择。

## 5 第二问结果与分析

### 5.1 验证期的费用权衡

图 2 比较不同余量的验证费用。岭回归配合 70% 分位数余量的十天总费用为 {summary['selection']['cost_yuan']:,.2f} 元，紧急费用为 {summary['selection']['emergency_cost_yuan']:,.2f} 元，在候选方案中最低。岭回归配合 90% 余量的验证期紧急费用为零，但总费用为 {float(val[(val.forecast=='ridge') & (val['quantile']==0.9)].cost_yuan.iloc[0]):,.2f} 元，更高的计划支出抵消了避免紧急购电的收益。

![图2 验证期余量与费用](../figures/q12/q2_validation.png)

图 2 一月验证期风险余量与费用的关系

四种策略在评价期采用相同初始 SOC：{manifest['evaluation_initial_soc']:,.2f} kWh，来源于从 1 月 1 日 6000 kWh 出发的共同热身运行。不同策略在后续产生各自的 SOC 轨迹，没有按天重置。验证期与全年比较均报告期末存量，避免忽略存量差异。

### 5.2 样本外预测与调度效果

表 3 为 334 天共 48,096 个时段上的预测误差。相对同期基线，岭回归对负载的改善较明显，光伏改善较小。图 3 展示题目指定的 3 月 20 日预测结果，单日图用于说明误差形态，整体评价以全期指标为准。

表 3 第二问样本外预测误差

{forecast_table}

![图3 指定日期的负载与光伏预测](../figures/q12/q2_forecast.png)

图 3 2025 年 3 月 20 日的日前预测与实际观测

表 4 与图 4 给出各策略的费用。岭回归无余量相对同期无余量已降低成本；在相同岭回归预测上增加 70% 余量，普通购电费增加，但紧急费用下降更多，最终总费用进一步降低 {100*(1-m['total_cost_yuan']/r0['total_cost_yuan']):.2f}%。这说明本题需要评价预测与调度的组合，而非只评价预测器。

表 4 第二问 2—12 月策略比较

{comparison}

![图4 全期费用分解](../figures/q12/q2_cost_comparison.png)

图 4 不同预测与余量策略的全期费用分解

选定策略累计紧急购电 {m['emergency_kwh']:,.2f} kWh，涉及 {m['emergency_intervals']} 个十分钟区间。未利用电量为 {m['spill_kwh']:,.2f} kWh，其中可能同时包含光伏富余和未吸收计划电量，当前账本不将其全部解释为弃光。该结果没有实现全年零紧急购电，也没有证明其为所有可行策略中的全局最优。

岭回归无余量与带余量策略在 12 月 31 日结束时均为 {m['final_soc_kwh']:,.2f} kWh，因此二者的主要费用差异不来自不同的期末电池存量。同期两组的期末 SOC 分别为 {base['final_soc_kwh']:,.2f} 与 {metrics['seasonal_q0.7']['final_soc_kwh']:,.2f} kWh；跨预测器的费用比较仍需注意这种存量差异。

### 5.3 指定日期结果

表 5 为题目指定四日的汇总。“全天购电量”在本稿及导出表中指普通计划购电量；紧急购电另列。“全天购电费”包含普通与紧急两部分。后续各表给出指定十分钟槽与四小时充放电量。

表 5 第二问指定日期汇总

{date_summary}

'''
    table_number=6
    for date in DATES:
        g=f[f.date==date]
        purchases=[[interval_label(h*6),float(g.plan_kwh.iloc[h*6])] for h in (10,12,14,16,18,20)]
        text+=f"### {date}\n\n表 {table_number} 给出指定时段购电量，表 {table_number+1} 为储能汇总，表 {table_number+2} 为连续紧急购电区间。\n\n"
        text+=f"表 {table_number} {date} 指定区间计划购电\n\n"+md_table(["时段","计划购电 / kWh"],purchases)+"\n\n"
        text+=f"表 {table_number+1} {date} 四小时充放电\n\n"+md_table(["时段","充电 / kWh","放电 / kWh"],blocks(g))+"\n\n"
        text+=f"表 {table_number+2} {date} 紧急购电\n\n"+md_table(["时段","紧急购电 / kWh"],emergency_runs(g) or [["无",0.0]])+"\n\n"
        table_number+=3
    text+=rf'''## 6 模型评价与后续改进

第一问的混合整数模型可直接对应题面物理约束，并通过 LP 下界和数值残差核验最优性与可行性。第二问将预测、风险余量和实际执行分开，保持历史信息边界，并以真实账本评价经济性，具有可解释和易复现的优点。

当前局限包括：一月份验证区间较短，无法充分代表全部季节；经验分位数没有给出联合概率保证；贪心实时平衡不一定是最优电池控制；名义日末 6000 kWh 的目标尚未系统调优；效率、时间标签及实时观测近似会影响结果。较优的全年表现来自本次实际回测，不应推广为任意未来数据下的保证。

在本机的一次运行中，包括预测候选验证、共同热身、策略筛选和四组全年回测的计算约为 {manifest['total_seconds']:.1f} 秒。每组全年共求解 334 个小规模日模型；该时间不包括代码开发、排错、写作与图表导出，也不代表第三、四问或更大场景模型的运行耗时。

后续可在不改变费用和物理口径的前提下，比较更充分的季节验证、终端储能目标、分位数预测与场景优化，并将第三问的日内预报更新接入同一调度框架。本稿不包含第三、四问结果。

## 参考文献

[1] 全国大学生数学建模竞赛组委会. 2026 年高教社杯全国大学生数学建模竞赛 C 题 微网与外部电网电力调控策略. 用户提供题面及附件 1、2、5.

[2] SciPy Developers. scipy.optimize.milp. https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html . 本文实际运行版本 1.17.1；在线文档用于接口与方法说明。

[3] scikit-learn Developers. Ridge. https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html . 本文按带截距的 L2 正则化目标以 NumPy 实现，未调用 scikit-learn 软件包。
'''
    # The abstract already identifies scope; keep project control notes outside manuscript.
    reportdir=Path("reports");reportdir.mkdir(exist_ok=True)
    (reportdir/"Q1_Q2初稿.md").write_text(text,encoding="utf-8")
    dump_json(out/"delivery_manifest.json",{"manuscript":"reports/Q1_Q2初稿.md","selected_strategy":selected,
              "figure_count":4,"table_count":table_number-1,"builder_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "skill_repo":"XiaoMaColtAI/math-modeling-skill","skill_commit":"3527fad922660397834a6167fc2b4c29ee64ba17"})
    print("Manuscript and plotting evidence built.",flush=True)


if __name__=="__main__":main()
