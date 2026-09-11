"""Small evidence-only non-bar figures using saved, verified computations."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.q12 import dump_json
SKILL=Path.home()/'.codex/skills/math-modeling/tools/figure/scripts'
sys.path.insert(0,str(SKILL))
from export_figure import export_figure
from visual_qa import audit_layout


def main():
    out=Path('figures/v2');out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False,'font.size':9,
        'axes.spines.top':False,'axes.spines.right':False})
    audits=[]
    def save(fig,name,claim):
        fig.canvas.draw();audit=audit_layout(fig)
        export_figure(fig,str(out/name),formats=['svg','png'],dpi=320,grayscale_preview=True)
        audits.append({'name':name,'claim':claim,'layout':audit});plt.close(fig)
    q1=json.loads(Path('artifacts/q12/q1_summary.json').read_text())
    sens=pd.read_csv('artifacts/q12/q1_efficiency_sensitivity.csv')
    value=float(sens.iloc[-1][next(c for c in sens if 'cost' in c)])
    fig,ax=plt.subplots(figsize=(6.3,2.5),layout='constrained')
    ax.scatter([q1['no_storage_cost'],q1['cost'],value],range(3),s=50,c=['#9D9EA3','#4D779B','#8074C8'])
    ax.set_yticks(range(3),['无储能','两侧各90%','往返90%']);ax.invert_yaxis();ax.set_xlabel('单日购电费用（元）')
    ax.set_xlim(30000,52000);ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    for i,v in enumerate([q1['no_storage_cost'],q1['cost'],value]):ax.annotate(f'{v:,.2f}',(v,i),xytext=(6,0),textcoords='offset points',va='center',fontsize=8)
    save(fig,'q1_efficiency_points','保持绝对费用口径，区分储能收益与效率解释')
    q2=json.loads(Path('artifacts/q12/q2_summary.json').read_text())['strategies']
    fig,ax=plt.subplots(figsize=(6.3,3.1),layout='constrained')
    labels=['同期 无余量','岭回归 无余量','同期 70%','岭回归 70%']
    for key,label,color,marker in [('normal_cost_yuan','计划费','#4D779B','o'),('emergency_cost_yuan','紧急费','#992224','s'),('total_cost_yuan','总费','#8074C8','D')]:
        ax.scatter([x[key]/1e4 for x in q2],np.arange(4),label=label,color=color,marker=marker,s=35)
    ax.set_yticks(range(4),labels);ax.invert_yaxis();ax.set_xlabel('334天费用（万元）');ax.set_xlim(0,2100)
    ax.legend(loc='lower left',bbox_to_anchor=(0,1),ncol=3,frameon=False);ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    save(fig,'q2_cost_points','计划费增加可减少更昂贵的紧急购电费')
    fig,ax=plt.subplots(figsize=(6.3,3),layout='constrained')
    for key,old,new,color in [('第三问','artifacts/q34/q3_m6_daily.csv','artifacts/v2/q3_v2_daily.csv','#4D779B'),
        ('第四问滚动','artifacts/q34/q4_3_seasonal_daily.csv','artifacts/v2/q4_3_seasonal_daily.csv','#8074C8')]:
        a=pd.read_csv(old);b=pd.read_csv(new);assert a.date.equals(b.date)
        ax.plot(pd.to_datetime(a.date),(a.total_cost_yuan-b.total_cost_yuan).cumsum()/1e4,label=key,color=color)
    ax.axhline(0,color='#9D9EA3',lw=.7);ax.set_ylabel('累计节省（万元）');ax.set_xlabel('2025年日期')
    ax.legend(loc='upper left',frameon=False);ax.grid(alpha=.18)
    save(fig,'rolling_savings','两项滚动策略收益在全年累计形成，不仅来自某个有利日期')
    dump_json(Path('artifacts/v2/figure_audit.json'),audits)


if __name__=='__main__':main()
