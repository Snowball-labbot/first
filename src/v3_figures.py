"""Competition-paper evidence figures; preserve all ten-minute decisions."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.q12 import dump_json
sys.path.insert(0,str(Path.home()/'.codex/skills/math-modeling/tools/figure/scripts'))
from export_figure import export_figure
from visual_qa import audit_layout
C={'grid':'#4D779B','soc':'#8074C8','load':'#3E608D','pv':'#F0C284','charge':'#7AB656','discharge':'#EF8B67','price':'#8D2F25','emergency':'#992224','base':'#9D9EA3'}

def main():
    out=Path('figures/v3');out.mkdir(parents=True,exist_ok=True);a=Path('artifacts/v3');audits=[]
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False,'font.size':9,'axes.labelsize':9,
        'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.65,'xtick.major.size':3,'ytick.major.size':3,'legend.fontsize':8,'svg.fonttype':'none'})
    def save(fig,name,claim):
        fig.canvas.draw();audit=audit_layout(fig)
        export_figure(fig,str(out/name),formats=['svg','png'],dpi=360,grayscale_preview=True)
        audits.append({'name':name,'claim':claim,'layout':audit});plt.close(fig)
    def grid(ax,axis='y'):ax.grid(axis=axis,color='#e8ebef',lw=.6);ax.set_axisbelow(True)
    q1=pd.read_csv(a/'q1_intervals.csv');qs=json.loads((a/'q1_summary.json').read_text())
    fig,axs=plt.subplots(2,1,figsize=(6.3,3.0),sharex=True,layout='constrained',height_ratios=[1.5,1])
    edges=np.arange(145)/6
    axs[0].stairs(q1.pv_kwh*6,edges,fill=True,color=C['pv'],alpha=.6,label='光伏')
    axs[0].stairs(q1.load_kwh*6,edges,baseline=None,color=C['load'],label='负载');axs[0].set_ylabel('功率 / kW');axs[0].legend(ncol=2,frameon=False)
    axs[1].stairs(q1.price,edges,baseline=None,color=C['price']);axs[1].set(ylabel='电价 / 元每kWh',xlabel='时刻 / h',xlim=(0,24),xticks=range(0,25,4))
    for ax in axs:grid(ax)
    save(fig,'raw_q1_inputs','第一问起点采样后的共同供需与电价输入')
    fig,axs=plt.subplots(3,1,figsize=(6.3,4.6),sharex=True,layout='constrained',height_ratios=[1.8,1,.7])
    edges=np.arange(145)/6;t=edges[:-1]
    axs[0].stairs(q1.charge_kwh*6,edges,fill=True,color=C['charge'],alpha=.42,label='充电')
    axs[0].stairs(-q1.discharge_kwh*6,edges,fill=True,color=C['discharge'],alpha=.6,label='放电')
    axs[0].stairs(q1.plan_kwh*6,edges,baseline=None,color=C['grid'],lw=1.15,label='外网购电')
    axs[0].stairs(q1.load_kwh*6,edges,baseline=None,color=C['load'],lw=.8,ls='--',label='负载')
    axs[0].stairs(q1.pv_kwh*6,edges,baseline=None,color='#C58A26',lw=.8,label='光伏')
    axs[0].set_ylabel('功率 / kW');axs[0].legend(ncol=5,loc='lower left',bbox_to_anchor=(0,1),frameon=False,columnspacing=1)
    S=np.r_[q1.soc_start_kwh.iloc[0],q1.soc_end_kwh];axs[1].plot(edges,S,color=C['soc'],lw=1.4)
    axs[1].fill_between(edges,1200,S,color=C['soc'],alpha=.1)
    for v in [1200,10800]:axs[1].axhline(v,color=C['soc'],ls='--',lw=.65)
    axs[1].set(ylim=(500,11800),yticks=[1200,6000,10800],ylabel='储电量 / kWh')
    axs[2].stairs(q1.price,edges,baseline=None,color=C['price'],lw=1.1);axs[2].set(ylabel='电价\n元/kWh',xlabel='时刻 / h',xticks=range(0,25,4),xlim=(0,24))
    for i,ax in enumerate(axs):grid(ax);ax.text(.01,.92,f'({chr(97+i)})',transform=ax.transAxes,va='top',fontsize=8)
    save(fig,'result_q1_dispatch','购电与充放电合并显示；SOC及电价共用时间轴；无平滑')
    sens=pd.read_csv(a/'q1_efficiency.csv');v90=float(sens.loc[(sens.roundtrip_efficiency-.9).abs()<1e-8,'cost'].iloc[0])
    fig,ax=plt.subplots(figsize=(6.3,2.6),layout='constrained');vals=np.array([qs['no_storage_cost'],qs['cost'],v90])/1e4
    bars=ax.barh(range(3),vals,height=.5,color=[C['base'],C['grid'],C['soc']]);ax.invert_yaxis()
    ax.set(yticks=range(3),yticklabels=['无储能','储能  两侧各90%','储能  往返90%'],xlabel='单日购电费用 / 万元',xlim=(0,5.55));grid(ax,'x')
    for b,v in zip(bars,vals):ax.text(v+.07,b.get_y()+b.get_height()/2,f'{v*1e4:,.2f} 元',va='center',fontsize=8)
    ax.set_title(f'主模型节省 {100*(1-vals[1]/vals[0]):.2f}%',loc='right',fontsize=10,color=C['grid'],fontweight='bold')
    save(fig,'result_q1_efficiency','零基线条形直接显示储能收益与效率损耗')
    q2=json.loads(Path('artifacts/q12/q2_summary.json').read_text())['strategies']
    fig,ax=plt.subplots(figsize=(6.3,2.8),layout='constrained');labels=['同期预测  无余量','岭回归  无余量','同期预测  70%余量','岭回归  70%余量']
    for i,s in enumerate(q2):
        p,e=s['normal_cost_yuan']/1e4,s['emergency_cost_yuan']/1e4
        ax.barh(i,p,height=.52,color=C['grid'],label='计划费' if i==0 else None)
        ax.barh(i,e,left=p,height=.52,color=C['emergency'],label='紧急费' if i==0 else None)
        ax.text(p/2,i,f'{p:,.1f}',ha='center',va='center',color='white',fontsize=8)
        ax.text(p+e+.02*2100,i,f'{p+e:,.2f}',va='center',fontsize=8,fontweight='bold' if i==3 else 'normal')
    ax.set(yticks=range(4),yticklabels=labels,xlabel='334天购电费用 / 万元',xlim=(0,2220));ax.invert_yaxis();grid(ax,'x')
    ax.legend(ncol=2,loc='lower left',bbox_to_anchor=(0,1),frameon=False)
    save(fig,'result_q2_cost','计划费与紧急费堆叠，总费用直接标注')
    sums={s['strategy']:s for s in json.loads((a/'summary.json').read_text())};sel=json.loads((a/'selection.json').read_text());mask=sel['q3']['mask']
    names=['不更新','06','12','06+12','18','06+18','12+18','06+12+18']
    fig,ax=plt.subplots(figsize=(6.3,3.1),layout='constrained')
    for i in range(8):
        s=sums[f'q3_m{i}'];e=s['emergency_cost_yuan']/1e4;normal=(s['total_cost_yuan']-s['emergency_cost_yuan'])/1e4
        ax.barh(i,normal,height=.56,color=C['grid'] if i==mask else '#A8C1D4',label='普通及调整费' if i==mask else None)
        ax.barh(i,e,left=normal,height=.56,color=C['emergency'],label='紧急费' if i==mask else None)
        ax.text(normal+e+12,i,f'{normal+e:,.2f}',va='center',fontsize=8,fontweight='bold' if i==mask else 'normal')
    ax.set(yticks=range(8),yticklabels=names,xlabel='334天购电费用 / 万元',xlim=(0,1710));ax.invert_yaxis();grid(ax,'x')
    ax.legend(ncol=2,loc='lower left',bbox_to_anchor=(0,1),frameon=False)
    save(fig,'result_q3_updates','同一余量下八种更新组合的成本构成')
    fig,axs=plt.subplots(1,2,figsize=(6.3,2.7),layout='constrained')
    v=pd.read_csv(a/'q3_validation.csv').pivot(index='q',columns='mask',values='cost')/1e4
    im=axs[0].imshow(v,aspect='auto',cmap='Blues',vmin=v.min().min(),vmax=v.max().max())
    for i in range(3):
        for j in range(8):axs[0].text(j,i,f'{v.iloc[i,j]:.1f}',ha='center',va='center',fontsize=6.5,color='white' if v.iloc[i,j]>58 else '#24364A')
    axs[0].set(xticks=range(8),xticklabels=['无','6','12','6/12','18','6/18','12/18','全'],yticks=range(3),yticklabels=['0','50%','70%'],xlabel='更新时间',ylabel='误差余量分位数',title='(a) 一月验证费 / 万元')
    for mode,color in [(3,C['grid']),(4,C['soc'])]:
        before=pd.read_csv(a/'q3_m0_daily.csv') if mode==3 else pd.read_csv(a/f'q4_2_{sel["prices"]["2"]}_daily.csv')
        after=pd.read_csv(a/f'q3_m{mask}_daily.csv') if mode==3 else pd.read_csv(a/f'q4_3_{sel["prices"]["3"]}_daily.csv')
        axs[1].plot(pd.to_datetime(after.date),(before.total_cost_yuan-after.total_cost_yuan).cumsum()/1e4,color=color,label=f'问题{mode}')
    axs[1].set(title='(b) 日内更新的累计收益',ylabel='累计节省 / 万元');axs[1].tick_params(axis='x',rotation=30);grid(axs[1]);axs[1].legend(frameon=False)
    save(fig,'process_q3_validation','验证选择与全年累计收益互相衔接')
    metrics=pd.read_csv('artifacts/v2/price_errors_by_issue.csv');fig,ax=plt.subplots(figsize=(6.3,2.8),layout='constrained')
    for i,(m,lab,col) in enumerate([('seasonal','同期预测',C['base']),('ridge','岭回归',C['grid']),('gru_mean','GRU集成',C['soc'])]):
        d=metrics[metrics.model==m];bars=ax.bar(np.arange(4)+(i-1)*.24,d.mae,width=.21,color=col,label=lab)
        for b,val in zip(bars,d.mae):ax.text(b.get_x()+b.get_width()/2,val+.001,f'{val:.3f}',ha='center',fontsize=7)
    ax.set(xticks=range(4),xticklabels=['00:00','06:00','12:00','18:00'],ylabel='价格 MAE / 元每kWh',xlabel='预测发布时刻',ylim=(0,.075));grid(ax)
    ax.legend(ncol=3,frameon=False,loc='upper right')
    save(fig,'result_q4_accuracy','四个发布时刻GRU误差均低于两种非神经网络基线')
    fig,axs=plt.subplots(1,2,figsize=(6.3,2.8),layout='constrained')
    mods=['seasonal','ridge','gru_mean','oracle'];labels=['同期','岭回归','GRU集成','真实电价对照'];colors=[C['base'],C['grid'],C['soc'],'#43745E']
    for mode,ax in zip([2,3],axs):
        ref=sums[f'q4_{mode}_seasonal']['total_cost_yuan'];vals=[(ref-sums[f'q4_{mode}_{m}']['total_cost_yuan'])/1e4 for m in mods]
        bars=ax.barh(range(4),vals,height=.5,color=colors);ax.invert_yaxis();ax.axvline(0,color='#555',lw=.65)
        ax.set(yticks=range(4),yticklabels=labels,title='日前策略' if mode==2 else '滚动策略',xlabel='相对同期预测节省 / 万元');grid(ax,'x')
        for b,v in zip(bars,vals):ax.annotate(f'{v:+.3f}',(v,b.get_y()+.25),xytext=(4 if v>=0 else -4,0),textcoords='offset points',ha='left' if v>=0 else 'right',va='center',fontsize=8)
        ax.set_xlim(-3.6,14);ax.set_xticks([-2,0,5,10])
        if mode==3:ax.set_yticklabels([])
    save(fig,'result_q4_cost','以零为基线显示节省金额；真实电价对照与可实施预测器分列')
    bound=pd.read_csv(a/'nominal_price_bound.csv').groupby('model')[['nominal_cost','oracle_lower','regret']].sum()
    fig,axs=plt.subplots(1,2,figsize=(6.3,2.7),layout='constrained',width_ratios=[1.25,1])
    vals=bound.loc[mods[:3],'regret'].to_numpy()/1e4
    bars=axs[0].bar(range(3),vals,color=colors[:3],width=.52);axs[0].set(xticks=range(3),xticklabels=labels[:3],ylabel='距真实电价名义最优 / 万元',ylim=(0,max(vals)*1.3));grid(axs[0])
    for i,v in enumerate(vals):axs[0].text(i,v+.35,f'{v:.2f}',ha='center',fontsize=8)
    axs[1].axis('off');ratio=100*bound.loc['gru_mean','regret']/bound.loc['gru_mean','nominal_cost']
    axs[1].text(.04,.88,'GRU 的名义费用差距',fontsize=10,transform=axs[1].transAxes)
    axs[1].text(.04,.53,f'{ratio:.3f}%',fontsize=28,color=C['soc'],fontweight='bold',transform=axs[1].transAxes)
    axs[1].text(.04,.15,'相同供需预测、初始储电量\n及功率容量约束；只改变价格信息',fontsize=8,linespacing=1.7,transform=axs[1].transAxes)
    save(fig,'result_q4_bound','在共同名义可行域内量化GRU距已知价格最优值的差距')
    dump_json(a/'figure_audit.json',audits)

if __name__=='__main__':main()
