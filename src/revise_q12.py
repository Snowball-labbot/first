"""Revised paper and publication figures, entirely from frozen Q1/Q2 evidence."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from src.q12 import dump_json, interval_label
from src.deliver_q12 import md_table, blocks, emergency_runs, DATES, COLORS

OUT=Path('artifacts/q12');DEST=Path('artifacts/q12_revision');FIG=Path('figures/q12_revision')
NAMES=['seasonal_q0','ridge_q0','seasonal_q0.7','ridge_q0.7']
SHORT=['同期 无余量','岭回归 无余量','同期 70%余量','岭回归 70%余量']


def main():
    DEST.mkdir(exist_ok=True);FIG.mkdir(exist_ok=True)
    sys.path.insert(0,str(Path.home()/'.codex/skills/math-modeling/tools/figure/scripts'))
    from export_figure import export_figure
    from visual_qa import audit_layout
    q1=pd.read_csv(OUT/'q1_intervals.csv')
    q1s=json.loads((OUT/'q1_summary.json').read_text())
    q2=json.loads((OUT/'q2_summary.json').read_text())
    metrics={v['strategy']:v for v in q2['strategies']};m=metrics['ridge_q0.7']
    val=pd.read_csv(OUT/'policy_validation.csv')
    f=pd.read_csv(OUT/'ridge_q0.7_intervals.csv.gz')
    seasonal=pd.read_csv(OUT/'seasonal_q0_intervals.csv.gz')
    daily=pd.read_csv(OUT/'q2_daily_metrics.csv');daily['month']=pd.to_datetime(daily.date).dt.month
    monthly=daily.groupby(['strategy','month'],as_index=False)[['total_cost_yuan','emergency_cost_yuan','emergency_kwh']].sum()
    monthly.to_csv(DEST/'monthly_costs.csv',index=False)
    err=[]
    for name,trace in [('同期',seasonal),('岭回归',f)]:
        month=pd.to_datetime(trace.date).dt.month
        for k,label in [('load','负载'),('pv','光伏')]:
            e=(trace['forecast_'+k+'_kwh']-trace[k+'_kwh'])*6
            for mo,g in e.groupby(month):err.append([name,label,int(mo),float(g.abs().mean()),float(np.sqrt((g*g).mean()))])
    errors=pd.DataFrame(err,columns=['forecast','variable','month','mae_kw','rmse_kw'])
    errors.to_csv(DEST/'monthly_forecast_errors.csv',index=False)
    # Statistical summaries are descriptive, not additional hyperparameter selection.
    rank=monthly.pivot(index='month',columns='strategy',values='total_cost_yuan')
    wins=int((rank['ridge_q0.7']<rank['seasonal_q0']).sum())
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','DejaVu Sans'],'axes.unicode_minus':False,
        'font.size':9,'axes.labelsize':9,'axes.titlesize':9.5,'legend.fontsize':8,
        'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.7,
        'xtick.major.width':.6,'ytick.major.width':.6,'svg.fonttype':'none','savefig.facecolor':'white'})
    audits={}
    def clean(ax):
        ax.set_axisbelow(True);ax.grid(axis='y',color='#E7E9ED',lw=.55)
        ax.tick_params(length=3,pad=3)
    def save(fig,name):
        issues=audit_layout(fig)
        if issues:raise RuntimeError((name,issues))
        export_figure(fig,str(FIG/name),formats=['png','svg'],dpi=320,
                      size_inches=tuple(fig.get_size_inches()),grayscale_preview=False,tight=False)
        svg=FIG/(name+'.svg');svg.write_text('\n'.join(s.rstrip() for s in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')
        audits[name]={'issues':issues,'width_inches':float(fig.get_size_inches()[0]),'dpi':320}
        plt.close(fig)
    edges=np.arange(145)/6;x=(edges[:-1]+edges[1:])/2
    fig,axs=plt.subplots(2,1,figsize=(6.25,3.8),sharex=True,layout='constrained',gridspec_kw={'height_ratios':[2,1]})
    axs[0].stairs(q1.pv_kwh*6,edges,fill=True,color=COLORS['pv_fill'],alpha=.65,label='光伏')
    axs[0].stairs(q1.load_kwh*6,edges,baseline=None,color=COLORS['load'],lw=1.4,label='负载')
    axs[0].set_ylabel('功率 / kW');axs[0].set_ylim(0,9800);axs[0].legend(loc='upper left',ncol=2,frameon=False)
    axs[1].stairs(q1.price,edges,baseline=None,color='#8D2F25',lw=1.4);axs[1].set_ylabel('电价 / (元/kWh)')
    for ax in axs:clean(ax);ax.set_xlim(0,24)
    axs[1].set_xticks(np.arange(0,25,4));axs[1].set_xlabel('时刻 / h');save(fig,'fig01_inputs')
    fig,allaxs=plt.subplots(4,1,figsize=(6.25,5.35),sharex=True,layout='constrained',gridspec_kw={'height_ratios':[.7,1.15,1,1.1]})
    priceax=allaxs[0];axs=allaxs[1:]
    priceax.stairs(q1.price,edges,baseline=None,color='#8D2F25',lw=1.2)
    priceax.set_ylabel('电价\n元/kWh');priceax.set_yticks([.4,.9,1.4]);priceax.set_ylim(.25,1.55)
    axs[0].stairs(q1.plan_kwh*6,edges,baseline=None,color=COLORS['grid'],lw=1.25,label='购电')
    axs[0].stairs((q1.load_kwh-q1.pv_kwh).clip(lower=0)*6,edges,baseline=None,color='#9D9EA3',lw=.9,ls='--',label='正净负载')
    axs[0].set_ylabel('购电功率\nkW');axs[0].set_ylim(0,11500);axs[0].set_yticks([0,4000,8000]);axs[0].legend(loc='upper center',ncol=2,frameon=False)
    axs[1].stairs(q1.charge_kwh*6,edges,fill=True,color='#7AB656',alpha=.8,label='充电（正）')
    axs[1].stairs(-q1.discharge_kwh*6,edges,fill=True,color='#EF8B67',alpha=.8,label='放电（负）')
    axs[1].axhline(0,color='#555555',lw=.65);axs[1].set_ylabel('充放电功率 / kW');axs[1].set_ylim(-6500,8000)
    axs[1].legend(ncol=2,loc='upper right',frameon=False)
    axs[2].axhspan(1200,10800,color=COLORS['soc'],alpha=.07)
    axs[2].plot(edges,np.r_[q1.soc_start_kwh.iloc[0],q1.soc_end_kwh],color=COLORS['soc'],lw=1.6)
    for b in [1200,10800]:axs[2].axhline(b,color=COLORS['soc'],lw=.7,ls='--')
    axs[2].set_yticks([1200,6000,10800]);axs[2].set_ylim(0,12000);axs[2].set_ylabel('储电量 / kWh')
    for ax in allaxs:clean(ax);ax.set_xlim(0,24)
    axs[2].set_xticks(np.arange(0,25,4));axs[2].set_xlabel('时刻 / h');save(fig,'fig02_dispatch')
    sens=pd.read_csv(OUT/'q1_efficiency_sensitivity.csv')
    fig,ax=plt.subplots(figsize=(6.25,2.5),layout='constrained')
    values=[q1s['no_storage_cost'],*sens.cost_yuan]
    bars=ax.barh(np.arange(3),np.array(values)/1e4,color=[COLORS['base'],COLORS['grid'],COLORS['soc']],height=.5)
    ax.set_yticks(range(3),['无储能','两侧效率各 90%','往返效率 90%']);ax.invert_yaxis()
    for b,v in zip(bars,values):ax.text(v/1e4+.08,b.get_y()+b.get_height()/2,f'{v/1e4:.4f}',va='center',fontsize=9)
    ax.set_xlim(0,5.6);ax.set_xlabel('单日购电费 / 万元');ax.grid(axis='x',color='#E7E9ED',lw=.5);ax.set_axisbelow(True)
    save(fig,'fig03_efficiency')
    fig,axs=plt.subplots(1,2,figsize=(6.25,2.9),layout='constrained')
    for j,(key,title) in enumerate([('cost_yuan','(a) 总费用'),('emergency_cost_yuan','(b) 紧急购电费')]):
        for method,color,marker,label in [('seasonal',COLORS['base'],'s','同期预测'),('ridge',COLORS['load'],'o','岭回归')]:
            v=val[val.forecast==method]
            axs[j].plot(range(4),v[key]/1e4,color=color,marker=marker,ms=4,lw=1.4,label=label)
        axs[j].set_title(title,loc='left');axs[j].set_xticks(range(4),['无余量','70%','80%','90%'])
        axs[j].set_xlabel('余量方案');axs[j].set_ylabel('十天费用 / 万元');clean(axs[j])
    axs[0].set_ylim(0,80);axs[1].set_ylim(0,20)
    axs[0].legend(frameon=False,loc='lower left');save(fig,'fig04_validation')
    fig,axs=plt.subplots(4,2,figsize=(6.25,6.6),layout='constrained',sharex=True,sharey='col')
    for i,date in enumerate(DATES):
        g=f[f.date==date]
        for j,key in enumerate(['load','pv']):
            ax=axs[i,j];ax.plot(x,g[key+'_kwh']*6,color=COLORS['actual'],lw=1.05,label='实际')
            ax.plot(x,g['forecast_'+key+'_kwh']*6,color=COLORS['forecast'],lw=1.2,ls='--',label='预测')
            ax.set_title(date,loc='left',fontsize=8.5);clean(ax);ax.set_xlim(0,24);ax.set_ylim(bottom=0)
            ax.set_ylabel(('负载' if j==0 else '光伏')+' / kW',fontsize=8)
            ax.set_xticks([0,6,12,18,24]);ax.tick_params(labelsize=8)
    sample=f[f.date.isin(DATES)]
    for j,key in enumerate(['load','pv']):
        upper=float(sample[[key+'_kwh','forecast_'+key+'_kwh']].to_numpy().max()*6*1.22)
        for ax in axs[:,j]:ax.set_ylim(0,upper)
    axs[0,0].legend(loc='upper right',ncol=2,frameon=False,fontsize=7.5)
    for ax in axs[-1]:ax.set_xlabel('时刻 / h')
    save(fig,'fig05_forecasts')
    fig,ax=plt.subplots(figsize=(6.25,3.1),layout='constrained')
    for i,name in enumerate(NAMES):
        y=3-i;normal=metrics[name]['normal_cost_yuan']/1e4;emergency=metrics[name]['emergency_cost_yuan']/1e4
        ax.barh(y,normal,height=.48,color=COLORS['grid'],label='计划购电费' if i==0 else None)
        ax.barh(y,emergency,left=normal,height=.48,color=COLORS['emergency'],label='紧急购电费' if i==0 else None)
        ax.text(normal+emergency+22,y,f'{normal+emergency:,.2f}',va='center',fontsize=8)
    ax.set_yticks([3,2,1,0],SHORT);ax.set_xlim(0,2250);ax.set_xlabel('2—12 月费用 / 万元')
    ax.legend(ncol=2,loc='upper center',bbox_to_anchor=(.53,1.18),frameon=False)
    ax.grid(axis='x',color='#E7E9ED',lw=.5);ax.set_axisbelow(True);save(fig,'fig06_cost')
    fig,axs=plt.subplots(2,1,figsize=(6.25,4.4),sharex=True,layout='constrained')
    for name,color,marker,label in [('seasonal_q0',COLORS['base'],'s','同期无余量'),('ridge_q0',COLORS['forecast'],'^','岭回归无余量'),('ridge_q0.7',COLORS['load'],'o','岭回归70%余量')]:
        g=monthly[monthly.strategy==name]
        for ax,key in zip(axs,['total_cost_yuan','emergency_cost_yuan']):ax.plot(g.month,g[key]/1e4,color=color,lw=1.4,marker=marker,ms=3,label=label)
    axs[0].set_ylabel('月总费用 / 万元');axs[1].set_ylabel('月紧急费用 / 万元')
    axs[0].legend(frameon=False,ncol=3,loc='upper center',bbox_to_anchor=(.5,1.2),fontsize=7.4)
    for ax in axs:clean(ax);ax.set_ylim(bottom=0)
    axs[1].set_xticks(range(2,13));axs[1].set_xlabel('月份');save(fig,'fig07_monthly_cost')
    fig,axs=plt.subplots(2,1,figsize=(6.25,3.1),layout='constrained')
    cmap=LinearSegmentedColormap.from_list('blue_mae',['#F5F8FB','#A8CBDF','#3E608D'])
    for ax,variable in zip(axs,['负载','光伏']):
        mat=errors[errors.variable==variable].pivot(index='forecast',columns='month',values='mae_kw').reindex(['同期','岭回归'])
        im=ax.imshow(mat,aspect='auto',cmap=cmap,vmin=0,vmax=errors[errors.variable==variable].mae_kw.max()*1.05)
        for i in range(2):
            for j in range(11):ax.text(j,i,f'{mat.iloc[i,j]:.0f}',ha='center',va='center',fontsize=7,color='white' if mat.iloc[i,j]>im.norm.vmax*.6 else '#243746')
        ax.set_yticks([0,1],['同期','岭回归']);ax.set_xticks(range(11),range(2,13));ax.set_title(variable+'月度 MAE / kW',loc='left')
        ax.tick_params(length=0);fig.colorbar(im,ax=ax,pad=.02,fraction=.03)
    axs[1].set_xlabel('月份');save(fig,'fig08_errors')
    dump_json(DEST/'figure_audit.json',audits)
    write_report(q1,q1s,q2,metrics,val,f,errors,wins)


def write_report(q1,a,q2,metrics,val,f,errors,wins):
    m=metrics['ridge_q0.7'];base=metrics['seasonal_q0'];r0=metrics['ridge_q0']
    pieces=[];tables=[];equations=[]
    def p(s):pieces.append(s.strip()+'\n\n')
    def eq(s):
        equations.append(s);p('$$\n'+s+'\n$$')
    def table(title,headers,rows):
        n=len(tables)+1;tables.append({'number':n,'title':title,'headers':headers,'rows':rows})
        p(f'表 {n} {title}');p(md_table(headers,rows));return n
    def fig(n,name,title,note):
        p(f'![{title}](../figures/q12_revision/{name}.png)');p(f'图 {n} {title}');p(note)
    def purchase(g):
        values=[float(g.plan_kwh.iloc[h*6]) for h in [10,12,14,16,18,20]]
        row1=sum([[interval_label(h*6),v] for h,v in zip([10,12,14],values[:3])],[])
        row2=sum([[interval_label(h*6),v] for h,v in zip([16,18,20],values[3:])],[])
        cost=float(((g.plan_kwh+5*g.emergency_kwh)*g.price).sum())
        return [row1,row2,['全天购电量',float(g.plan_kwh.sum()),'全天购电费',cost,'—','—']]
    def storage(g):
        b=blocks(g)
        return [b[0]+b[1],b[2]+b[3],b[4]+b[5],['00:00 储电量',float(g.soc_start_kwh.iloc[0]),'—','24:00 储电量',float(g.soc_end_kwh.iloc[-1]),'—']]
    p('# 考虑预测误差的微网日前购电与储能调度')
    p('## 摘 要')
    p('针对光伏发电、小区负载与分时电价共同影响的微网购电问题，建立统一的母线能量平衡和储能状态模型，分别研究已知曲线下的单日最优调度，以及供需未知时的日前计划与实时补购。')
    p(f'针对第一问，在充电、放电效率各为 90% 的解释下，将十分钟购电、充放电和弃用电量作为连续变量，以二元变量保证充放电互斥，并约束日初与日末储电量相同。采用混合整数线性规划求得全天计划购电 {a["plan_kwh"]:,.2f} kWh、购电费 {a["cost"]:,.2f} 元，较无储能基线降低 {a["saving_percent"]:.2f}%。整数解与线性松弛下界一致，支持当前模型下数值精度内的最优性。')
    p(f'针对第二问，将同期预测和岭回归与日前调度连接，以历史净负载预测误差分位数构造余量。通过 1 月验证选择岭回归与 70% 余量，在 2—12 月 334 天进行顺序回测，普通与紧急购电总费用为 {m["total_cost_yuan"]/1e4:,.2f} 万元，比同期无余量低 {100*(1-m["total_cost_yuan"]/base["total_cost_yuan"]):.2f}%，比岭回归无余量低 {100*(1-m["total_cost_yuan"]/r0["total_cost_yuan"]):.2f}%。验证期 90% 余量虽消除紧急购电，总费用反而更高，说明可靠性改善必须与计划支出共同评价。')
    p('模型检查覆盖能量平衡、SOC 连续性、功率和容量边界、充放电互斥及费用复算。第二问结论限于所检验策略，尚未证明随机控制意义下的全局最优；短验证期、效率与时间标签解释仍是需要进一步核对的因素。')
    p('关键词：微网调度；混合整数线性规划；岭回归；预测误差；日前购电')
    p('## 一 问题重述')
    p('题面研究小区光伏、负载、储能与外部电网之间的电力调控 [1]。储能可以在低价或光伏富余时吸收电量，在高价或供电不足时释放电量；调度既要满足负载，也要尽可能节省购电费用。本文只处理前两问。')
    p('第一问给定每天重复的电价、负载和单日光伏预测，要求每天 00:00 制定全天购电计划，且日初日末储电量相同。需报告指定十分钟时段的购电量、全天总量和费用，以及四小时充放电汇总。第二问中负载与光伏逐日变化，正常购电仍按计划量收费，供电缺口通过五倍交易电价的紧急购电补足，需输出 2—12 月每日完整策略及四个指定日期的结果。')
    p('## 二 问题分析')
    p('第一问是已知输入曲线下的跨时段资源分配。线性回归不负责决定何时充电；购电、电池和负载之间的能量约束才是主模型。加入二元变量后可直接保证同一时段不同时充放电，避免事后修复改变费用与可行性。')
    p('第二问的预测误差具有不对称经济后果：低估净负载可能触发五倍电价补购，高估则可能产生仍需付费的富余计划电量。因此先预测负载与光伏，再构造风险余量并求购电计划，最后用实际观测执行与计费。预测误差用于评价预测器，实际购电总费用用于评价完整策略，两者不能互相替代。')
    p('## 三 模型假设与数据处理')
    p('### 3.1 参数及工作假设')
    p('统一参数见表 1。功率上限按微网母线侧定义，所有决策电量使用 kWh。题面“充放电效率为 90%”可能存在单程与往返解释差异，主实验采用两侧各 90%，并对另一解释单独进行敏感性分析。')
    table('储能参数与时间离散',['参数','数值','性质'],[['额定容量','12000 kWh','题面给定'],['允许储电量','1200—10800 kWh','题面给定'],['最大充放电功率','5000 kW','题面给定'],['初始储电量','6000 kWh','1 月 1 日 00:00 给定'],['充电／放电效率','0.9／0.9','主实验解释'],['时段长度','1/6 h','十分钟离散']])
    p('（1）将每个功率值解释为以时间标签为右端点的十分钟区间平均值。由此原始 00:10 对应 00:00—00:10，原始 00:00+1 对应 23:50—24:00。结果副本按该时间轴统一标签；该解释并非题面明确说明的采样定义。')
    p('（2）不设置题面未给出的售电收入与折旧价格，允许不能使用的电量被弃用。普通购电按计划量结算，富余计划量不退款。电池磨损成本没有纳入当前目标。')
    p('（3）实际执行近似每十分钟内功率恒定、当前供需可即时观测并平衡。该近似只服务于区间内的充放电和紧急购电，不允许日前读取当天真实曲线。')
    p('（4）第二问实际 SOC 连续跨日。日前名义轨迹的日末下限取 6000 kWh，作为防止计划耗空电池的策略设置；不强制实际日末回到 6000，也不按天重置电池。')
    p('### 3.2 输入审计与时间边界')
    p('附件 1 有 144 个时段，附件 2 的负载与光伏各有 365×144＝52,560 个观测。读取后检查到完整的 2025 年日期、相同的负载和光伏时间轴，未发现缺失、负数或重复日期，未无依据删除峰值。附件 1 混合存储了时间类型与字符串，统一转换分钟后核对 10、20、…、1440。电量按下式换算：')
    eq(r'L_{d,t}=P^{\mathrm{load}}_{d,t}\Delta t,\qquad V_{d,t}=P^{\mathrm{PV}}_{d,t}\Delta t,\qquad \Delta t=\frac{1}{6}\ \mathrm{h}.')
    p('独立重读原始工作簿确认：附件 1 的时间列含 60 个时间类型单元格和 84 个字符串，均已规范化；附件 2 的两类序列各 52,560 项无缺失、非有限值或负数，且无重复日期或完全重复的日曲线。全局四分位距规则未标记超界点，但这一检查不能证明不存在局部测量误差。')
    p('因此，本次预处理没有执行填补、删点、缩尾或平滑，只执行时间格式与单位规范化。光伏有 23,540 个零值，其本身不是缺失标记，保留在原始记录与回测中。预测值的非负截断属于模型输出规则，训练集标准化属于特征处理，均不等同于修改实际观测。')
    p('实际数据的测量不确定性没有单独给出，因此不添加虚构置信区间。全文图线来自原始输入或保存的实际计算结果，时段内不做平滑插值。')
    p('## 四 符号说明')
    p('下文沿用表 2 的符号。单日模型省略日期下标，日内区间用 1—144，状态包含 145 个边界点；跨日计算另带日期下标。')
    table('主要符号及单位',['符号','含义','单位'],[[r'$d,t$','日期与十分钟时段','—'],[r'$L_{d,t},V_{d,t}$','负载与光伏电量','kWh'],[r'$\hat L_{d,t},\hat V_{d,t}$','日前负载与光伏预测','kWh'],[r'$g_{d,t},e_{d,t}$','计划购电与紧急购电','kWh'],[r'$c_{d,t},d_{d,t}$','母线侧充电与放电','kWh'],[r'$w_{d,t}$','不能利用的富余电量','kWh'],[r'$S_{d,t}$','区间起点的储电量','kWh'],[r'$p_t$','固定分时交易电价','元/kWh'],[r'$\eta_c,\eta_d$','充电与放电效率','—'],[r'$z_t$','充电状态二元变量','—'],[r'$\lambda,q$','岭惩罚强度与余量分位数','—'],[r'$r_{d,t}(q)$','非负净负载预测余量','kWh']])
    p('日期下标 d 与放电变量的字母 d 通过下标位置区分；为简化实现，程序字段分别使用 date 和 discharge_kwh。')
    p('## 五 第一问的模型建立与求解')
    p('### 5.1 供需结构与决策目标')
    p('已给曲线及固定电价如图 1 所示。光伏集中在白天，而负载覆盖全天，储能调度应同时响应供需差额和分时价格。电价使用独立面板，避免功率与价格共用坐标造成误读。')
    fig(1,'fig01_inputs','第一问供需曲线与分时电价','图中每一阶梯对应一个十分钟平均功率或电价，光伏阴影为功率曲线下区域，不作为置信带。')
    p('目标是最小化全天计划购电费：')
    eq(r'\min C_1=\sum_{t=1}^{144}p_tg_t.')
    p('以母线侧收支写能量守恒，将允许的富余供电显式记为未利用电量：')
    eq(r'g_t+V_t+d_t=L_t+c_t+w_t,\qquad g_t,w_t\geq0.')
    p('充电损耗发生在进入储能时，放电损耗发生在从储能输出至母线时，因而状态方程为：')
    eq(r'S_{t+1}=S_t+\eta_c c_t-\frac{d_t}{\eta_d},\qquad 1200\leq S_t\leq10800.')
    p('SOC 上下界施加于全部 145 个状态点，状态递推与其他时段约束对应 t＝1，…，144。令每时段最大母线侧充放电量 M＝5000/6 kWh，用二元变量直接限制互斥：')
    eq(r'0\leq c_t\leq Mz_t,\qquad 0\leq d_t\leq M(1-z_t),\qquad z_t\in\{0,1\}.')
    p('第一问满足以下初始和终端条件，避免利用电池初始存量净放电造成虚假节省：')
    eq(r'S_1=S_{145}=6000.')
    p('将上述关系集中写成一般日模型，决策变量为购电、充放电、未利用电量、储电量和状态变量。给定不同供需输入与初末状态条件时，可复用以下结构：')
    eq(r'\boxed{\left\{\begin{aligned}\min_{g,c,d,w,S,z}\quad &\sum_{t=1}^{144}p_tg_t\\\mathrm{s.t.}\quad &g_t+V_t+d_t=L_t+c_t+w_t,\\&S_{t+1}=S_t+\eta_c c_t-d_t/\eta_d,\\&1200\leq S_t\leq10800,\quad g_t,w_t\geq0,\\&0\leq c_t\leq Mz_t,\quad0\leq d_t\leq M(1-z_t),\\&z_t\in\{0,1\},\quad S_1=S_{145}=6000.\end{aligned}\right.}')
    p('上述模型有 865 个变量，其中 144 个为二元变量。以 SciPy 1.17.1 的 milp 接口调用 HiGHS [2]，相对间隙目标设为 10⁻⁷，每日求解时间上限为 30 秒；超时或无可行解时应停止并报告，而非将空结果视为成功。')
    p('### 5.2 调度结果与指定时段')
    p(f'计算得到全天购电量 {a["plan_kwh"]:,.2f} kWh、费用 {a["cost"]:,.2f} 元。购电与储能轨迹见图 2，指定时段购电和四小时充放电分别见表 3、表 4。')
    fig(2,'fig02_dispatch','第一问电价驱动的购电与储能运行','自上而下为电价、购电与正净负载、充放电、SOC。所有阶梯保留十分钟决策，不作平滑。购电超过正净负载的部分用于充电；SOC 阴影为允许范围。')
    table('第一问指定时段购电量及全天费用',['时间段','购电量','时间段','购电量','时间段','购电量'],purchase(q1))
    p('表中电量单位为 kWh，全天购电费单位为元。')
    table('第一问四小时充放电及日初日末储电量',['时间段','充电量','放电量','时间段','充电量','放电量'],storage(q1))
    p('表内所有电量单位为 kWh，充放电量采用母线侧口径。四小时内可先充后放，汇总行两者均正不违反十分钟互斥。图中尖峰主要对应集中充电：22:00—22:10 负载约 3309.39 kW、光伏为零，充电 5000 kW，故购电约 8309.39 kW。相邻时段电价为 0.3859、0.4368 元/kWh，模型分别安排满功率充电与不充电。')
    p('当前目标只计购电费，未计充电切换成本或功率爬坡限制，因此低价区间内也可能出现零散充电。这是模型边界，不能由图形尖峰直接判为原始数据异常。固定放电与未利用电量、保持费用不变的充电变差最小化诊断未获得实质不同的轨迹，不能据此声称存在平滑且同成本的替代方案。若需要更平稳的实际操作，应另加爬坡约束或费用容差内的次级目标，重新计算并比较成本。')
    p('### 5.3 最优性检验与效率解释')
    p(f'删除整数限制得到线性松弛下界 {a["lp_cost_lower_bound"]:,.8f} 元，与整数解目标之差为 {a["lp_gap_yuan"]:.8f} 元，求解器相对间隙为零。在本题输入与约束口径下，这支持数值精度内的全局最优性。能量平衡最大残差约 {a["audit"]["max_balance_residual_kwh"]:.2e} kWh，SOC 递推与容量、功率边界均通过复核。')
    p('以每时段正净负载直接购电构造无储能基线：')
    eq(r'g_t^{(0)}=\max(L_t-V_t,0),\qquad C_1^{(0)}=\sum_t p_tg_t^{(0)}.')
    p(f'该基线费用为 {a["no_storage_cost"]:,.2f} 元，主模型节省 {a["saving_percent"]:.2f}%。效率解释的对照见图 3：若总往返效率为 0.9，并对称取两侧效率为平方根 0.9，费用为 33,801.50 元。该试验只改变效率，不能与主实验混为同一组结果。')
    fig(3,'fig03_efficiency','第一问储能收益与效率解释对照','所有柱形从零开始。前两项比较储能作用，后两项比较效率解释；主文及 Excel 均对应“两侧效率各 90%”。')
    p('## 六 第二问的预测与日前策略')
    p('### 6.1 训练与评价的时间顺序')
    p('以 1 月 22—31 日作为验证窗，选择岭回归惩罚与风险余量。2 月 1 日起固定这些选择规则，执行至 12 月 31 日。模型每七天更新一次，最多使用最近 60 个已结束日期；评价过程中已观察到的数据可以进入后续更新，尚未发生的数据不进入当前决策。这是顺序样本外回测，而不是把全年随机拆分。')
    p('一月份共同热身从 1 月 1 日的 6000 kWh 开始；首日无历史时用附件 1 作为冷启动参考，随后不足七天用近三日均值，积累七天后用日／周同期。验证期初 SOC 为 6244.256891 kWh，评价期初为 9902.811288 kWh，各候选策略都从同一状态出发。冷启动的附件 1 仅作为明确的初始化假设，不当作全年可提前获得的预报。')
    p('### 6.2 同期基线与岭回归预测')
    p('对负载或光伏电量序列 y，同期基线取昨日与上周同日相同时间槽的均值：')
    eq(r'\hat y_{d,t}^{\mathrm{seasonal}}=\frac{y_{d-1,t}+y_{d-7,t}}{2}.')
    p('岭回归采用 21 个特征：昨日、前日、上周同日的同槽值，三日和七日同槽均值、七日同槽标准差、昨日全天均值和近三日全天均值共八项；前三阶日内正余弦六项；星期指示七项。日期及时间属于决策时已知的日历信息。标准化均值与尺度仅在当次训练集上估计，常量特征尺度置 1。')
    eq(r'\min_{\beta,b}\sum_{i\in\mathcal T_d}(y_i-b-\widetilde{x}_i^{\mathsf T}\beta)^2+\lambda\|\beta\|_2^2.')
    p('截距不惩罚，负载和光伏分别拟合。按验证 MAE 比较 λ＝1、10、100，均选 1；实现采用 NumPy 线性方程求解，与带截距岭目标一致 [3]。从 1 月 15 日开始具备拟合条件，之后每七日重新拟合。预测截断为非负；某槽过去七日光伏全零时，该槽预测置零，日出日落季节变化可能使此规则产生滞后。')
    p('评价指标采用功率单位的 MAE 与 RMSE；不使用夜间分母为零的普通 MAPE：')
    eq(r'\mathrm{MAE}=\frac{1}{n}\sum_i|P_i-\widehat P_i|,\qquad\mathrm{RMSE}=\sqrt{\frac{1}{n}\sum_i(P_i-\widehat P_i)^2}.')
    p('### 6.3 净负载误差余量与名义优化')
    p('定义历史净负载误差及只包含过去信息的误差样本池：')
    eq(r'\varepsilon_{j,s}=(L_{j,s}-V_{j,s})-(\hat L_{j,s}-\hat V_{j,s}).')
    eq(r'\mathcal E_{d,t}=\{\varepsilon_{j,s}:\max(2,d-28)\leq j<d,\ 1\leq s\leq144,\ |s-t|\leq3\}.')
    p('日期下标以 1 月 1 日为 d＝1；排除首日冷启动误差，最多池化 28 个已结束日期和目标槽前后三槽。跨日边界不绕回，不足 28 天时仅取已有历史。余量规则为：')
    eq(r'r_{d,t}(q)=\max\{0,Q_q(\mathcal E_{d,t})\}.')
    p('无余量候选直接设 r＝0，与“取零分位数”区分。对 q＝0.7、0.8、0.9，分位数使用样本排序后的线性插值。将预测负载加余量作为名义需求，求解第五节同一物理模型：')
    eq(r'L_t^{\mathrm{nom}}=\hat L_{d,t}+r_{d,t}(q),\qquad V_t^{\mathrm{nom}}=\hat V_{d,t},\qquad S_{d,145}^{\mathrm{nom}}\geq6000.')
    p('70% 分位数不是“全天 70% 概率不缺电”的保证。名义优化只最小化计划费，五倍紧急购电的影响通过验证期对余量方案的筛选间接体现，不能据此称为已精确求解随机规划。')
    p('### 6.4 实时执行与跨日状态')
    p('当天普通购电计划固定后，定义当前供需剩余。对非负剩余尽量充电，对缺口尽量放电，并分别受可用空间、储电量和功率限制：')
    eq(r'u_t=g_t+V_t-L_t.')
    eq(r'c_t=\min\left\{\max(u_t,0),M,\frac{10800-S_t}{\eta_c}\right\}.')
    eq(r'd_t=\min\left\{\max(-u_t,0),M,\eta_d(S_t-1200)\right\}.')
    eq(r'e_t=\max(-u_t-d_t,0),\qquad w_t=\max(u_t-c_t,0).')
    p('以上规则使同一时段仅有充电或放电，SOC 仍按状态方程更新，实际日末传给次日：')
    eq(r'S_{d+1,1}=S_{d,145}.')
    p('所有供电缺口由紧急购电补足。全年评价费用定义为：')
    eq(r'C_2=\sum_{d,t}p_tg_{d,t}+5\sum_{d,t}p_te_{d,t}.')
    p('将第二问策略概括如下。记 Ω 为第一问中除初末等式之外的物理可行域，输入替换为带余量预测，日初状态取真实已知值；G 表示本节的贪心实时平衡规则：')
    eq(r'\boxed{\left\{\begin{aligned}(g^{\mathrm{plan}},\ldots)&\in\arg\min_{(g,c,d,w,S,z)\in\Omega}\sum_t p_tg_t,\\L^{\mathrm{nom}}&=\hat L+r(q),\quad V^{\mathrm{nom}}=\hat V,\\S_1^{\mathrm{nom}}&=S_1^{\mathrm{actual}},\quad S_{145}^{\mathrm{nom}}\geq6000,\\(c_t,d_t,e_t,w_t)&=\mathcal G(g_t^{\mathrm{plan}},L_t,V_t,S_t),\\C_2&=\sum_{d,t}p_t(g_{d,t}^{\mathrm{plan}}+5e_{d,t}).\end{aligned}\right.}')
    p('其中 Ω 中每一时段的平衡使用上式名义输入；最后一行是实际策略评价费用，不是声称日前已知实际 e 的优化目标。余量 q 仅由一月验证费用选择，之后冻结。')
    p('实际储能动作可以偏离名义动作，但普通计划购电不能按真实曲线事后改写。这一贪心控制具有可行性与因果性，不保证跨时段的实时经济最优。')
    p('## 七 第二问的结果与检验')
    p('### 7.1 验证期选择与紧急购电权衡')
    p('验证结果见表 5 与图 4。各方案使用相同验证初始 SOC，但期末存量不同，因此除费用外同时列出期末储电量，不把存量差异隐藏在成本比较中。')
    table('一月份十天验证结果',['预测器','余量','总费/元','紧急费/元','期末SOC/kWh'],[[('同期' if r.forecast=='seasonal' else '岭回归'),('无' if r['quantile']==0 else f'{r["quantile"]:.0%}'),float(r.cost_yuan),float(r.emergency_cost_yuan),float(r.end_soc_kwh)] for _,r in val.iterrows()])
    fig(4,'fig04_validation','验证期风险余量与费用的权衡','横轴为四种候选方案，其中“无余量”是独立基线。折线只辅助比较候选值，不表示连续参数的精确响应。')
    p('岭回归 70% 余量的验证费为 509,757.47 元，其中紧急费 8,765.44 元；90% 余量紧急费为零，但总费升至 633,664.05 元。两者期末储电量相差约 2416 kWh，故不能完全忽略存量影响；当前目标仍按题面购电费用评价，不另添加缺乏依据的残值收入。')
    p('### 7.2 全期预测误差与季节变化')
    p('按表 6 比较 334 天共 48,096 个十分钟区间的功率预测误差，岭回归在负载预测上的改善大于光伏。四个指定日期的曲线对照见图 5，整年误差仍以全期统计为准。')
    table('第二问全期预测误差',['预测器','负载MAE','负载RMSE','光伏MAE','光伏RMSE'],[[label,*[metrics[n][k] for k in ['load_mae_kw','load_rmse_kw','pv_mae_kw','pv_rmse_kw']]] for label,n in [('同期','seasonal_q0'),('岭回归','ridge_q0.7')]])
    p('上述误差单位均为 kW，光伏指标包含夜间零值，不能直接等同于白天发电时段的预测精度。')
    fig(5,'fig05_forecasts','四个指定日期的负载与光伏日前预测','各列共用纵轴尺度，日期由题目指定。实线为实际观测，虚线为岭回归预测，不加入平滑后虚构的尖峰。')
    p('### 7.3 全期购电费用与运行约束')
    p('策略费用分解如图 6，数值及期末存量见表 7。相同初始状态保证比较具有共同起点，实际状态在全年内自行连续演化。')
    table('第二问全期费用及期末储电量',['策略','计划费/万元','紧急费/万元','总费/万元','期末SOC/kWh'],[[SHORT[i],metrics[n]['normal_cost_yuan']/1e4,metrics[n]['emergency_cost_yuan']/1e4,metrics[n]['total_cost_yuan']/1e4,metrics[n]['final_soc_kwh']] for i,n in enumerate(NAMES)])
    fig(6,'fig06_cost','第二问四组策略的全期费用分解','蓝色为普通计划购电费，深红为紧急购电费；条形右端标注两者合计。主策略由一月份验证选择。')
    p(f'主策略总费用 {m["total_cost_yuan"]:,.2f} 元，较同期无余量低 {100*(1-m["total_cost_yuan"]/base["total_cost_yuan"]):.2f}%，较岭回归无余量低 {100*(1-m["total_cost_yuan"]/r0["total_cost_yuan"]):.2f}%。后两组期末 SOC 均为 {m["final_soc_kwh"]:,.2f} kWh，因此此处的余量增益没有被不同期末存量混淆。')
    p(f'主策略紧急购电累计 {m["emergency_kwh"]:,.2f} kWh，涉及 {m["emergency_intervals"]} 个十分钟区间，不等同于同样数量的独立事件。未利用电量为 {m["spill_kwh"]:,.2f} kWh，其中可包含未消纳光伏和富余计划购电，不能全部称为弃光。')
    p(f'按月费用见图 7，主策略在 11 个评价月份中有 {wins} 个月的总费用低于同期无余量。月度划分仅用于描述已固定策略的季节表现，未用于重新选超参数；月总费也受到月份天数和负载规模影响，不宜直接将其解读为单位供电效率。')
    fig(7,'fig07_monthly_cost','固定策略的月度总费用与紧急费用','上面板为含紧急费用的月总费，下面板为其中的紧急费用。三条曲线依次分离预测改进和风险余量的作用。')
    p('月度预测 MAE 进一步见图 8。两块热力图各用自身的颜色上限，不能直接按跨面板颜色深浅比较负载与光伏误差；应读取格内数值。该图用于观察季节变化，不提供未计算的置信区间。')
    fig(8,'fig08_errors','同期预测与岭回归的月度误差','每格为对应月份全部十分钟区间的 MAE，单位 kW；数值为整数显示，统计文件保留完整精度。')
    p('### 7.4 题目指定日期的结果')
    p('以下表 8—表 15 按题面并排布局给出四个日期的指定时段购电、全天量费及四小时储能汇总。购电量指普通计划量，全天购电费包含普通与紧急两部分；紧急量在表 16 单列。')
    for date in DATES:
        p(f'{date} 的购电结果见表 {len(tables)+1}，储能结果见表 {len(tables)+2}。')
        g=f[f.date==date]
        p('#### '+date+' 的运行结果')
        table(date+' 指定时段购电与全天费用',['时间段','购电量','时间段','购电量','时间段','购电量'],purchase(g))
        table(date+' 充放电与边界储电量',['时间段','充电量','放电量','时间段','充电量','放电量'],storage(g))
    rows=[];runlists=[emergency_runs(f[f.date==date]) or [['无',0.0]] for date in DATES]
    for i in range(max(map(len,runlists))):rows.append(sum([r[i] if i<len(r) else ['—','—'] for r in runlists],[]))
    table('四个指定日期的紧急购电',['3月20日时段','电量','6月21日时段','电量','9月23日时段','电量','12月21日时段','电量'],rows)
    p('以上电量单位为 kWh、费用单位为元。3 月 20 日与 6 月 21 日无紧急购电；9 月 23 日发生于 20:20—20:30，12 月 21 日发生于 07:50—08:00。连续正紧急购电槽合并为一个区间，不跨日合并。')
    p('## 八 模型检验与适用范围')
    p('### 8.1 数值与因果检查')
    p('复算以保存的完整精度逐时结果为依据，再逐项核对 Excel。检查包括供电平衡、SOC 递推、跨日状态衔接、非负电量、功率与容量限制、充放电互斥以及普通和紧急费用。CSV 保留 17 位有效数字，论文显示两位小数，两位小数表不用于重新计算约束残差。')
    p('程序测试用可手算的两时段套利验证最优目标，用电池容量边界验证充放电与紧急补购，用改变未来输入后的前缀不变性检查信息边界。全期物理残差在 10⁻⁵ kWh 容差内，未发现违约记录。数值可行性检查不能替代对时间标签和效率解释的审题判断。')
    p('### 8.2 局限与后续改进')
    p('第一问是给定假设下的确定性最优解；没有计入电池磨损，不能据此保证高频切换在实际设备中最经济。若增加磨损惩罚或平滑约束，应重新求解并作为新模型报告，不可只平滑购电图来暗中修改方案。')
    p('第二问的经验分位数没有联合供电可靠性保证，一月份十天验证不足以覆盖所有季节。实时贪心控制、6000 kWh 名义终端目标与短历史训练窗均为可改进环节，现有实验没有证明其优于所有神经网络或场景优化方案。')
    p('若继续扩展，可比较滚动的多季节验证、终端储能目标和显式场景优化，并在第三问中引入题目提供的日内预报。当前前两问不需要训练 GRU 或 LSTM 才能成立，是否采用复杂预测器应由同等信息条件下的费用与误差共同决定。')
    p('## 九 结论')
    p(f'已知供需曲线时，采用带互斥约束的 MILP 可得到费用 {a["cost"]:,.2f} 元的单日调度，最优性由线性松弛下界和整数解共同支持。供需未知时，岭回归与风险余量连接日前调度，在本次 334 天回测中获得 {m["total_cost_yuan"]/1e4:,.2f} 万元总费用。适度余量减少紧急补购，但零紧急购电不是成本最小的同义词。')
    p('本文统一了电量单位、损耗、计划付费与跨日状态的计算口径。结论依赖于所列效率解释、时间离散及即时平衡假设；第三、四问尚未纳入本稿。')
    p('## 参考文献')
    p('[1] 全国大学生数学建模竞赛组委会. 2026 年高教社杯全国大学生数学建模竞赛 C 题：微网与外部电网电力调控策略. 用户提供题面与附件.')
    p('[2] SciPy Developers. scipy.optimize.milp[EB/OL]. https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html. 访问日期：2026-09-10；运行版本：1.17.1.')
    p('[3] scikit-learn Developers. Ridge[EB/OL]. https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html. 访问日期：2026-09-10. 本文按该目标以 NumPy 实现，未调用 scikit-learn.')
    p('## 附录 支撑材料与运行说明')
    p('数学计算程序为 src/q12.py，七项基础测试位于 tests/test_q12.py，逐时结果核对程序为 src/verify_q12.py。主结果保存在 artifacts/q12，含 result1.xlsx、result2.xlsx、四组逐时压缩记录、逐日指标与验证比较。修订图表和分月统计分别位于 figures/q12_revision 与 artifacts/q12_revision，初稿重建程序为 src/revise_q12.py。')
    p('使用 Python 3.12.14、NumPy 2.3.5、SciPy 1.17.1、pandas 2.2.3 和 Matplotlib 3.10.9。安装依赖后，从仓库根目录运行模型，并通过 --data-root 指向原题目录。前两问整套四组回测在本机一次执行约 61.7 秒，不含程序开发与文档制作。原始附件需由使用者另行取得，不能仅凭论文复现原始输入。当前是前两问初稿，完整代码附件与 AI 使用记录应在全篇定稿时统一整理。')
    report=Path('reports/Q1_Q2修订稿.md');report.write_text(''.join(pieces).rstrip()+'\n',encoding='utf-8')
    Path('reports/Q1_Q2公式.tex').write_text('% LaTeX equation source for the editable Word equations.\n'+'\n\n'.join('\\[\n'+s+'\n\\]' for s in equations)+'\n',encoding='utf-8')
    dump_json(DEST/'report_manifest.json',{'report':str(report),'tables':tables,'display_equations':equations,
              'figure_count':8,'table_count':len(tables),'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'selected_strategy':'ridge_q0.7','months_better_than_seasonal_no_reserve':wins})
    print(f'Revised manuscript: {len(equations)} display equations, {len(tables)} tables, 8 figures.')


if __name__=='__main__':main()
