"""Evidence figures with consistent colors, actual values, and vector cells."""
from pathlib import Path
import argparse,json,sys,shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.q34_data import read_extended
from src.q12 import dump_json,forecasts
from src.deliver_q12 import DATES,COLORS


def main():
    p=argparse.ArgumentParser();p.add_argument('--data-root',required=True);args=p.parse_args()
    out=Path('artifacts/q34');dest=Path('figures/full');dest.mkdir(exist_ok=True)
    data,_=read_extended(args.data_root);q3=json.loads((out/'q3_selection.json').read_text())
    q4=json.loads((out/'q4_summary.json').read_text());prices=np.load(out/'price_forecasts.npz')
    sys.path.insert(0,str(Path.home()/'.codex/skills/math-modeling/tools/figure/scripts'))
    from export_figure import export_figure
    from visual_qa import audit_layout
    sys.path.insert(0,str(Path('插图配色').resolve()));from mgstyle import set_style
    set_style();plt.rcParams.update({'font.size':9,'axes.labelsize':9,'axes.titlesize':9,'legend.fontsize':8,'svg.fonttype':'none'})
    audits={}
    def save(fig,name):
        issues=audit_layout(fig)
        if issues:raise RuntimeError((name,issues))
        export_figure(fig,str(dest/name),formats=['png','svg'],dpi=320,size_inches=tuple(fig.get_size_inches()),grayscale_preview=True,tight=False)
        for file in dest.glob(name+'*.svg'):file.write_text('\n'.join(s.rstrip() for s in file.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')
        audits[name]={'layout':issues,'png':str(dest/(name+'.png'))};plt.close(fig)
    def clean(ax):ax.grid(axis='y',color='#E7E9ED',lw=.6);ax.set_axisbelow(True)
    x=(np.arange(144)+.5)/6
    fig,axs=plt.subplots(2,1,figsize=(6.25,3.4),layout='constrained',sharex=True)
    for ax,key,c in zip(axs,['load','pv'],[COLORS['load'],COLORS['pv']]):
        ax.plot(data['dates'],data[key].mean(1)*6,color=c,lw=1);ax.set_ylabel(('负载' if key=='load' else '光伏')+'日均 / kW');clean(ax)
    save(fig,'raw_q2_annual')
    pred,_=forecasts(data,'ridge',(1.,1.));day=171
    fig,ax=plt.subplots(figsize=(6.25,3.2),layout='constrained')
    ax.plot(x,data['pv'][day]*6,color=COLORS['actual'],lw=1.4,label='实际光伏')
    for v,c in zip(range(4),['#9D9EA3','#7895C1','#3E608D','#8074C8']):
        ax.plot(x[v*36:],data['pv_issued'][day,v,v*36:]*6,color=c,ls='--',lw=1.05,label=f'{v*6:02d}:00 预报')
    ax.set(xlim=(0,24),ylim=(0,12000),xlabel='时刻 / h',ylabel='光伏功率 / kW');ax.legend(ncol=3,frameon=False,loc='upper center');clean(ax)
    save(fig,'raw_q3_forecasts')
    val=pd.read_csv(out/'q3_validation.csv');mat=val.pivot(index='quantile',columns='mask',values='total_cost_yuan')/1e4
    fig,ax=plt.subplots(figsize=(6.25,2.5),layout='constrained')
    im=ax.pcolormesh(np.arange(9)-.5,np.arange(4)-.5,mat.to_numpy(),cmap='Blues',shading='flat',rasterized=False)
    ax.grid(False)
    ax.invert_yaxis();ax.set_yticks(range(3),['0','70%','90%']);ax.set_xticks(range(8),['无','06','12','06+12','18','06+18','12+18','全部'])
    ax.set(xlabel='日内更新时刻',ylabel='余量分位数')
    for i in range(3):
        for j in range(8):ax.text(j,i,f'{mat.iloc[i,j]:.2f}',ha='center',va='center',fontsize=8,color='white' if im.norm(mat.iloc[i,j])>.6 else '#253B53')
    cb=fig.colorbar(im,ax=ax,pad=.02);cb.set_label('一月验证费 / 万元');cb.solids.set_rasterized(False)
    save(fig,'process_q3_validation')
    summaries=[json.loads((out/f'q3_m{i}_summary.json').read_text()) for i in range(8)]
    labels=['无','06','12','06+12','18','06+18','12+18','全部']
    fig,axs=plt.subplots(1,2,figsize=(6.25,3.5),layout='constrained',sharey=True)
    for ax,key,title,color in zip(axs,['total_cost_yuan','emergency_cost_yuan'],['全部费用','紧急费用'],[COLORS['grid'],COLORS['emergency']]):
        a=np.array([r[key] for r in summaries])/1e4
        ax.barh(range(8),a,height=.6,color=[color if i==q3['mask'] else '#ABB7C4' for i in range(8)])
        ax.set_yticks(range(8),labels);ax.set_xlabel(title+' / 万元');ax.set_xlim(0,max(a)*1.24)
        for i,v in enumerate(a):ax.text(v+max(a)*.02,i,f'{v:.1f}',va='center',fontsize=8)
    axs[0].invert_yaxis();save(fig,'result_q3_cost')
    selected=pd.read_csv(out/f'q3_m{q3["mask"]}_intervals.csv.gz');g=selected[selected.date=='2025-09-23']
    fig,axs=plt.subplots(2,1,figsize=(6.25,3.7),layout='constrained',sharex=True)
    edges=np.arange(145)/6
    axs[0].stairs(g.original_plan_kwh*6,edges,baseline=None,ls='--',color='#9D9EA3',label='午夜计划')
    axs[0].stairs(g.plan_kwh*6,edges,baseline=None,color=COLORS['grid'],label='最终有效计划');axs[0].legend(ncol=2,frameon=False,loc='upper center')
    axs[0].set_ylabel('购电功率 / kW');axs[0].set_ylim(0,max(g.plan_kwh.max(),g.original_plan_kwh.max())*7.5)
    axs[1].plot(edges,np.r_[g.soc_start_kwh.iloc[0],g.soc_end_kwh],color=COLORS['soc']);axs[1].axhspan(1200,10800,color=COLORS['soc'],alpha=.07)
    axs[1].set(xlim=(0,24),ylim=(0,12000),xlabel='时刻 / h',ylabel='储电量 / kWh')
    for ax in axs:
        clean(ax)
        for h in [6,12,18]:
            if q3['mask']&(1<<(h//6-1)):ax.axvline(h,color='#925EB0',ls=':',lw=.8)
    save(fig,'result_q3_dispatch')
    fig,ax=plt.subplots(figsize=(6.25,2.8),layout='constrained')
    a=data['actual_price'];ax.fill_between(data['dates'],a.min(1),a.max(1),color='#EF8B67',alpha=.35,label='日内最小至最大')
    ax.plot(data['dates'],a.mean(1),color='#8D2F25',lw=1,label='日均');ax.set_ylabel('实际电价 / (元/kWh)');ax.legend(ncol=2,frameon=False);clean(ax);save(fig,'raw_q4_price')
    logs=json.loads((out/'price_fit_log.json').read_text());fig,ax=plt.subplots(figsize=(6.25,2.8),layout='constrained')
    for seed,color in zip([17,42,2026],['#7895C1','#3E608D','#8074C8']):
        history=next(r['history'] for r in logs if r['seed']==seed and r['fit_day']==151)
        ax.plot([h['epoch'] for h in history],[h['inner_validation_mae'] for h in history],color=color,label=f'种子 {seed}')
    ax.set(xlabel='训练轮数',ylabel='内部验证 MAE / (元/kWh)');ax.legend(frameon=False);clean(ax);save(fig,'process_q4_learning')
    fig,axs=plt.subplots(2,2,figsize=(6.25,4.8),layout='constrained',sharex=True,sharey=True)
    for ax,date in zip(axs.ravel(),DATES):
        d=int(np.where(data['dates']==date)[0][0]);ax.plot(x,data['actual_price'][d],color=COLORS['actual'],lw=1,label='实际')
        ax.plot(x,prices['ridge'][d,0],color=COLORS['load'],ls='--',lw=1,label='岭回归')
        ax.plot(x,prices['gru_mean'][d,0],color=COLORS['soc'],ls=':',lw=1.3,label='GRU集成')
        ax.set_title(date,loc='left');ax.set(xlim=(0,24),ylim=(0,2),xlabel='时刻 / h',ylabel='电价 / (元/kWh)');clean(ax)
    axs[0,0].legend(ncol=3,frameon=False,fontsize=7,loc='upper left');save(fig,'result_q4_forecast')
    names=['seasonal','ridge','gru17','gru42','gru2026','gru_mean'];labels=['同期','岭回归','GRU 17','GRU 42','GRU 2026','GRU集成']
    fig,axs=plt.subplots(1,2,figsize=(6.25,3.8),layout='constrained',sharey=True)
    for mode,ax in zip([2,3],axs):
        a=[next(r['total_cost_yuan'] for r in q4 if r['mode']==mode and r['forecast']==n)/1e4 for n in names]
        ax.scatter(a,range(6),color=[COLORS['base'],COLORS['load'],*[COLORS['soc']]*4],s=30)
        ax.set_yticks(range(6),labels);ax.set_xlabel('总费用 / 万元');ax.set_title('日前策略' if mode==2 else '滚动策略',loc='left')
        width=max(a)-min(a);pad=max(width*.3,.5);ax.set_xlim(min(a)-pad,max(a)+pad*3)
        for i,v in enumerate(a):ax.text(v+pad*.2,i,f'{v:.2f}',va='center',fontsize=8)
        clean(ax)
    axs[0].invert_yaxis();save(fig,'result_q4_cost')
    mapping={'raw_q1_inputs':'fig01_inputs','process_q1_efficiency':'fig03_efficiency','result_q1_dispatch':'fig02_dispatch',
             'process_q2_validation':'fig04_validation','result_q2_forecast':'fig05_forecasts','result_q2_cost':'fig06_cost'}
    for name,source in mapping.items():
        for ext in ['png','svg']:shutil.copyfile(Path('figures/q12_revision')/(source+'.'+ext),dest/(name+'.'+ext))
    dump_json(out/'figure_audit.json',audits)


if __name__=='__main__':main()
