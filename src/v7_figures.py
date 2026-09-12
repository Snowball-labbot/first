"""Figures aligned with the final model; quantities, timing and valuation."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.q12 import dump_json
from src.v3_figures import C
sys.path.insert(0,str(Path.home()/'.codex/skills/math-modeling/tools/figure/scripts'))
from export_figure import export_figure
from visual_qa import audit_layout
OUT=Path('figures/v7')
def main():
    OUT.mkdir(exist_ok=True,parents=True);audits=[]
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False,'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','pdf.fonttype':42})
    def save(fig,name,sources,claim):
        fig.canvas.draw();a=audit_layout(fig);export_figure(fig,str(OUT/name),formats=['png','svg'],dpi=340,grayscale_preview=True);plt.close(fig)
        audits.append(dict(name=name,sources=sources,claim=claim,layout=a))
    def grid(ax):ax.grid(color='#e6e9ed',lw=.5);ax.set_axisbelow(True)
    f=pd.read_csv('artifacts/v7/q1_intervals.csv');edges=np.arange(145)/6
    fig,ax=plt.subplots(2,1,figsize=(6.3,3.1),sharex=True,layout='constrained')
    for col,label,color in [('load_kwh','负载',C['load']),('pv_kwh','光伏',C['pv'])]:ax[0].stairs(f[col]*6,edges,baseline=None,label=label,color=color)
    ax[0].set_ylabel('功率 / kW');ax[0].legend(frameon=False,ncol=2)
    ax[1].stairs(f.price,edges,baseline=None,color=C['price']);ax[1].set(ylabel='电价 / 元每kWh',xlabel='时刻 / h',xticks=range(0,25,4),xlim=(0,24))
    for a in ax:grid(a)
    save(fig,'q1_inputs',['artifacts/v7/q1_intervals.csv'],'统一终点区间均值的第一问输入')
    fig,ax=plt.subplots(3,1,figsize=(6.3,4.5),sharex=True,layout='constrained',height_ratios=[1.4,1,.7])
    ax[0].stairs(f.plan_kwh*6,edges,baseline=None,color=C['grid'],label='普通购电')
    ax[0].stairs(f.charge_kwh*6,edges,fill=True,color=C['charge'],alpha=.4,label='充电')
    ax[0].stairs(-f.discharge_kwh*6,edges,fill=True,color=C['discharge'],alpha=.5,label='放电')
    ax[0].set_ylabel('功率 / kW');ax[0].legend(frameon=False,ncol=3,loc='upper right')
    ax[1].plot(edges,np.r_[f.soc_start_kwh.iloc[0],f.soc_end_kwh],color=C['soc'])
    for y in [1200,10800]:ax[1].axhline(y,color='#999',ls='--',lw=.6)
    ax[1].set(ylabel='储电量 / kWh',yticks=[1200,6000,10800],ylim=(500,11500))
    ax[2].stairs(f.price,edges,baseline=None,color=C['price']);ax[2].set(ylabel='电价\n元/kWh',xlabel='时刻 / h',xticks=range(0,25,4),xlim=(0,24))
    for a in ax:grid(a)
    save(fig,'q1_dispatch',['artifacts/v7/q1_intervals.csv'],'第一问最优购电与可执行储能轨迹')
    v=pd.read_csv('artifacts/v7/q1_value.csv');cap=pd.read_csv('artifacts/v7/capacity_value.csv')
    fig,ax=plt.subplots(1,2,figsize=(6.3,2.8),layout='constrained')
    ax[0].plot(v.soc_kwh/1000,v.cost_yuan/10000,'o-',color=C['soc'],ms=3);ax[0].set(xlabel='初始储电量 / MWh',ylabel='后续购电费 / 万元',title='(a) 固定期末6 MWh')
    ax[1].plot(cap.usable_capacity_kwh/1000,cap.flexibility_value/10000,'s-',color=C['grid'],ms=4)
    ax[1].scatter([9.6],[cap.flexibility_value.iloc[4]/10000],color=C['price'],zorder=3,s=30)
    ax[1].set(xlabel='可用容量 / MWh',ylabel='单日灵活性价值 / 万元',title='(b) 固定初末6 MWh',ylim=(0,1.6))
    for a in ax:grid(a)
    save(fig,'storage_value',['artifacts/v7/q1_value.csv','artifacts/v7/capacity_value.csv'],'库存价值与可用容量的边际收益递减')
    fig,ax=plt.subplots(2,1,figsize=(6.3,3.8),sharex=True,layout='constrained')
    for prefix,label,color in [('q2','库存价值控制',C['grid'])]:
        b=pd.read_csv(f'artifacts/v5b/{prefix}_greedy_daily.csv');n=pd.read_csv(f'artifacts/v5b/{prefix}_{"value_zero" if prefix=="q2" else "value"}_daily.csv')
        ax[0].plot(pd.to_datetime(n.date),(b.total_cost_yuan-n.total_cost_yuan).cumsum()/10000,label=label,color=color)
        ax[1].plot(pd.to_datetime(n.date),(n.emergency_kwh-b.emergency_kwh).cumsum(),label=label,color=color)
    ax[0].set_ylabel('累计节费 / 万元');ax[0].legend(frameon=False,ncol=2)
    ax[1].set_ylabel('累计紧急量增量 / kWh');ax[1].tick_params(axis='x',rotation=25)
    for a in ax:grid(a)
    save(fig,'q2_value_gain',['artifacts/v5b/q2_value_zero_daily.csv','corresponding greedy daily trace'],'问题二价值控制节费并不要求紧急电量下降')
    base=pd.read_csv('artifacts/v3/q3_m0_daily.csv');roll=pd.read_csv('artifacts/v3/q3_m7_daily.csv');online=pd.read_csv('artifacts/v5/q3_online_daily.csv');last=pd.read_csv('artifacts/v5b/q3_value_release_daily.csv')
    fig,ax=plt.subplots(1,2,figsize=(6.3,2.8),layout='constrained')
    ax[0].plot(pd.to_datetime(roll.date),(base.total_cost_yuan-roll.total_cost_yuan).cumsum()/10000,color=C['grid']);ax[0].set(title='(a) 日内更新',ylabel='累计节费 / 万元')
    for f0,f1,label,color in [(roll,online,'负载修正',C['load']),(online,last,'库存价值',C['soc'])]:ax[1].plot(pd.to_datetime(last.date),(f0.total_cost_yuan-f1.total_cost_yuan).cumsum()/10000,label=label,color=color)
    ax[1].set(title='(b) 顺序加入的改进',ylabel='累计节费 / 万元');ax[1].legend(frameon=False)
    for a in ax:grid(a);a.tick_params(axis='x',rotation=25)
    save(fig,'q3_information_value',['artifacts/v3/q3_m0_daily.csv','artifacts/v3/q3_m7_daily.csv','artifacts/v5/q3_online_daily.csv','artifacts/v5b/q3_value_release_daily.csv'],'固定预测下先比较信息更新，再顺序分解增益')
    metrics=pd.read_csv('artifacts/v2/price_errors_by_issue.csv');fig,ax=plt.subplots(figsize=(6.3,2.7),layout='constrained')
    for model,label,color,marker in [('seasonal','同期',C['base'],'o'),('ridge','岭回归',C['grid'],'s'),('gru_mean','GRU',C['soc'],'^')]:
        z=metrics[metrics.model==model];ax.plot([0,6,12,18],z.mae,label=label,color=color,marker=marker)
    ax.set(xticks=[0,6,12,18],xlabel='发布时刻 / h',ylabel='价格MAE / 元每kWh',ylim=(0,.075));ax.legend(ncol=3,frameon=False);grid(ax)
    save(fig,'q4_accuracy',['artifacts/v2/price_errors_by_issue.csv'],'同一发布与目标的价格预测误差')
    dump_json('artifacts/v7/figure_audit.json',audits);print('Six numerical figures exported')
if __name__=='__main__':main()
