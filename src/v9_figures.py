"""V8-frozen numerical payloads, unified V9 vector figure design."""
from pathlib import Path
import json,hashlib
import numpy as np
from scipy.io import loadmat
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle,Polygon
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'figures/v9';OUT.mkdir(parents=True,exist_ok=True)
D=loadmat(ROOT/'artifacts/v8/figure_data.mat',squeeze_me=True)
C=dict(actual='#30353B',grid='#4F6D8A',pv='#D9A441',charge='#4F9B8F',discharge='#D2785D',soc='#776B9D',forecast='#6E8FB4',emergency='#A84A4A',base='#B8BEC4',line='#E4E6E8')
plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':8.5,'axes.titlesize':9,'axes.labelsize':8.5,'xtick.labelsize':8,'ytick.labelsize':8,'text.color':C['actual'],'axes.labelcolor':C['actual'],'xtick.color':C['actual'],'ytick.color':C['actual'],'axes.edgecolor':C['actual'],'axes.linewidth':.6,'lines.linewidth':1.1,'pdf.fonttype':42,'svg.fonttype':'none','axes.unicode_minus':False,'legend.fontsize':8,'legend.frameon':False,'savefig.facecolor':'white'})
h=D['hours'];e=np.arange(145)/6;dates=['3月20日','6月21日','9月23日','12月21日'];manifest=[]
def fig(height,rows=1,cols=1,**kw):
    f,a=plt.subplots(rows,cols,figsize=(15.5/2.54,height/2.54),squeeze=False,**kw)
    f.subplots_adjust(left=.12,right=.97,bottom=.15,top=.86,hspace=.60,wspace=.40)
    for ax in a.flat:
        ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',color=C['line'],linewidth=.55);ax.set_axisbelow(True);ax.tick_params(length=2.5,width=.6)
    return f,a
def panel(a,k,title=''):
    a.set_title(f'({k})  {title}',loc='left',fontweight='bold',pad=8)
def time(a,label=True):
    a.set_xlim(0,24);a.set_xticks(np.arange(0,25,6));
    if label:a.set_xlabel('时刻 / h')
    else:a.tick_params(labelbottom=False)
def step(a,v,**kw):return a.stairs(v,e,baseline=0 if kw.get('fill') else None,**kw)
def leg(f,handles,labels,n=3,y=.99):f.legend(handles,labels,loc='upper center',bbox_to_anchor=(.53,y),ncol=n,columnspacing=1.3,handlelength=2.2)
def save(f,name,keys):
    # User-mandated exceptions: exact V7 source palette for figures 3, 6, 8.
    if name=='result_q1_dispatch':
        a,b,c=f.axes
        for p,col in zip(a.patches,['#7AB656','#EF8B67','#4D779B','#3E608D','#C58A26']):p.set_color(col)
        a.patches[0].set_alpha(.42);a.patches[1].set_alpha(.6)
        for line in b.lines:line.set_color('#8074C8')
        b.collections[0].set_facecolor('#8074C8');b.collections[0].set_alpha(.1)
        c.patches[0].set_color('#8D2F25')
        for ax in [a,b,c]:ax.set_xticks(range(0,25,4))
        for legend in list(f.legends):legend.remove()
        leg(f,*a.get_legend_handles_labels(),5)
    if name=='q2_forecasts':
        for ax in f.axes:
            ax.lines[0].set_color('#CD3B42');ax.lines[1].set_color('#7895C1')
        for legend in list(f.legends):legend.remove()
        leg(f,*f.axes[0].get_legend_handles_labels(),2,y=1.003)
    if name=='q3_forecasts':
        for line,col in zip(f.axes[0].lines,['#CD3B42','#9D9EA3','#7895C1','#3E608D','#8074C8']):
            line.set_color(col)
            if col!='#CD3B42':line.set_linestyle('--')
        for legend in list(f.legends):legend.remove()
        leg(f,*f.axes[0].get_legend_handles_labels(),3)
    f.savefig(OUT/(name+'.svg'))
    with plt.rc_context({'svg.fonttype':'path'}):f.savefig(OUT/(name+'_word.svg'))
    f.savefig(OUT/(name+'.pdf'));f.savefig(OUT/(name+'.png'),dpi=600)
    Image.open(OUT/(name+'.png')).convert('L').save(OUT/(name+'_gray.png'))
    manifest.append(dict(name=name,width_cm=15.5,height_cm=float(f.get_figheight()*2.54),source_keys=keys,source_hashes={k:hashlib.sha256(np.asarray(D[k]).tobytes()).hexdigest() for k in keys}))
    plt.close(f);print(name,flush=True)

# Layered schematic: an open physical bus, then information and decision lanes.
f,a=fig(10.8);a=a[0,0];a.set_axis_off();a.set_position([.025,.025,.95,.95]);a.set_xlim(0,100);a.set_ylim(0,100)
def txt(x,y,s,**kw):a.text(x,y,s,ha='center',va='center',**kw)
txt(7,91,'物理系统',fontweight='bold');a.plot([24,92],[86,86],color=C['line'],lw=1.5)
for x,label,color in [(26,'负载',C['actual']),(47,'光伏',C['pv']),(68,'外网购电',C['grid']),(89,'储能 / SOC',C['soc'])]:
    a.plot([x,x],[86,89],color=color,lw=1.3);txt(x,94,label,color=color,fontweight='bold');txt(x,82,{'负载':'用电需求','光伏':'清洁出力','外网购电':'合同与补购','储能 / SOC':'充放电与库存'}[label],fontsize=8)
txt(57,74,'共同约束：能量平衡 · 功率与容量边界 · 储能递推',fontsize=8.5)
for y in [69,51,33,15]:a.axhline(y,xmin=.01,xmax=.99,color=C['line'],lw=.7)
xs=[9,33,61,87]
for x,s in zip(xs,['信息递进','预测与风险','购电决策','实时运行']):txt(x,65,s,fontweight='bold')
rows=[(56,'问题一','供需与电价已知','确定性线性规划','最优充放电'),(43,'问题二','岭回归 + 分位数余量','午夜固定合同','库存价值控制'),(25,'问题三','日内光伏预报更新','非对称结算调单','可调单库存估值'),(7,'问题四','波动价格及预测误差','日前 / 滚动两分支','实际价格结算')]
for y,q,forecast,decision,control in rows:
    for x,s in zip(xs,[q,forecast,decision,control]):txt(x,y,s,fontsize=8.4,fontweight='bold' if x==9 else 'normal')
    for x0,x1 in [(45,49),(73,77)]:a.annotate('',(x1,y),(x0,y),arrowprops={'arrowstyle':'->','color':C['base'],'lw':.8})
save(f,'modeling_overview',[])

f,aa=fig(7.8,2,1,gridspec_kw={'height_ratios':[2,1]});a,b=aa[:,0]
step(a,D['q1_pv_kwh']*6,fill=True,color=C['pv'],alpha=.25,label='光伏');step(a,D['q1_load_kwh']*6,color=C['actual'],label='负载');a.set_ylabel('功率 / kW');panel(a,'a','供需错峰');time(a,False)
step(b,D['q1_price'],color=C['actual']);b.set_ylabel('电价 / 元/kWh');panel(b,'b','分时电价');time(b);leg(f,*a.get_legend_handles_labels(),2)
save(f,'raw_q1_inputs',['q1_pv_kwh','q1_load_kwh','q1_price'])

f,aa=fig(11.39172,3,1,gridspec_kw={'height_ratios':[2,1.12,.82]});f.subplots_adjust(top=.88,bottom=.11,hspace=.35);a,b,c=aa[:,0]
step(a,D['q1_charge_kwh']*6,fill=True,color=C['charge'],alpha=.45,label='充电');step(a,-D['q1_discharge_kwh']*6,fill=True,color=C['discharge'],alpha=.48,label='放电');step(a,D['q1_plan_kwh']*6,color=C['grid'],label='外网购电');step(a,D['q1_load_kwh']*6,color=C['actual'],ls='--',label='负载');step(a,D['q1_pv_kwh']*6,color=C['pv'],label='光伏');a.set_ylabel('功率 / kW');a.axhline(0,color=C['base'],lw=.6);time(a,False)
s=np.r_[D['q1_soc_start_kwh'],D['q1_soc_end_kwh'][-1]];b.plot(e,s,color=C['soc']);b.fill_between(e,1200,s,color=C['soc'],alpha=.09)
for y in [1200,10800]:b.axhline(y,color=C['soc'],ls=':',lw=.7)
b.set_yticks([1200,6000,10800]);b.set_ylabel('储电量 / kWh');time(b,False);step(c,D['q1_price'],color=C['actual']);c.set_ylabel('电价\n元/kWh');time(c)
for ax,k in zip([a,b,c],'abc'):ax.text(.01,.90,f'({k})',transform=ax.transAxes,fontweight='bold')
leg(f,*a.get_legend_handles_labels(),5);save(f,'result_q1_dispatch',['q1_charge_kwh','q1_discharge_kwh','q1_plan_kwh','q1_load_kwh','q1_pv_kwh','q1_soc_start_kwh','q1_soc_end_kwh','q1_price'])

f,aa=fig(7.5,1,2);f.subplots_adjust(left=.14,wspace=.65);a,b=aa[0];v=D['q1_waterfall'][[0,2,1]]
a.barh(range(3),v,height=.43,color=[C['base'],C['soc'],C['grid']]);a.set_yticks(range(3),['无储能','实际效率','无损储能']);a.invert_yaxis();a.set_xlim(0,6.7);a.grid(axis='x');a.set_xlabel('日费用 / 万元');panel(a,'a','储能费用收益')
for i,x in enumerate(v):a.text(x+.1,i,f'{x:.3f}',va='center',fontsize=7.6)
b.plot(D['q1_efficiency'],D['q1_sensitivity'],'o-',color=C['grid'],mfc='white',ms=4);b.scatter([81],[D['q1_sensitivity'][2]],s=55,facecolors='none',edgecolors=C['actual'],zorder=5);b.set_xlabel('往返效率 / %');b.set_ylabel('日费用 / 万元');panel(b,'b','效率敏感性');b.set_xticks([64,81,100]);save(f,'q1_efficiency',['q1_waterfall','q1_efficiency','q1_sensitivity'])

f,aa=fig(7.6,1,2)
for j,key in enumerate(['validation_cost','validation_emergency']):
 a=aa[0,j]
 for k,label in enumerate(['同期预测','岭回归']):a.plot(np.arange(4)+(k-.5)*.08,D[key][k],['o','s'][k],color=[C['base'],C['grid']][k],mfc='white',ms=5,label=label)
 a.set_xticks(range(4),['无余量','70%','80%','90%']);a.set_xlabel('误差余量分位数');a.set_ylabel('验证期费用 / 万元');panel(a,'ab'[j],['总费用','紧急购电费'][j])
aa[0,0].scatter([1.04],[D['validation_cost'][1,1]],s=85,facecolors='none',edgecolors=C['actual']);leg(f,*aa[0,0].get_legend_handles_labels(),2);save(f,'q2_validation',['validation_cost','validation_emergency'])

f,aa=fig(16.368,4,2,sharex=True,sharey='col');f.subplots_adjust(left=.12,right=.98,top=.93,bottom=.07,hspace=.44,wspace=.32)
for i in range(4):
 for j,(actual,pred,name) in enumerate([('q2_load_kwh','q2_forecast_load_kwh','负载'),('q2_pv_kwh','q2_forecast_pv_kwh','光伏')]):
  a=aa[i,j];a.plot(h,D[actual][i]*6,color=C['actual'],label='实际');a.plot(h,D[pred][i]*6,'--',color=C['forecast'],label='预测');a.set_ylim(0,9000 if j==0 else 10000);a.set_ylabel(name+' / kW');time(a,i==3);panel(a,chr(97+i*2+j),dates[i])
leg(f,*aa[0,0].get_legend_handles_labels(),2,y=1.003);save(f,'q2_forecasts',['q2_load_kwh','q2_forecast_load_kwh','q2_pv_kwh','q2_forecast_pv_kwh'])

f,aa=fig(8.1,1,2,gridspec_kw={'width_ratios':[1.8,1]});f.subplots_adjust(left=.19,wspace=.38);a,b=aa[0];v=D['q2_cost'][[0,1,3,4]];tot=v.sum(axis=1);y=np.arange(4)
for i in y:a.plot([0,v[i,0]],[i,i],color=C['grid'],lw=1.8);a.plot([v[i,0],tot[i]],[i,i],color=C['emergency'],lw=1.8)
a.scatter(v[:,0],y,color=C['grid'],s=20,label='普通计划费');a.scatter(tot,y,color=C['emergency'],marker='s',s=18,label='含紧急费的总费用');a.set_yticks(y,['同期无余量','岭回归预测','增加70%余量','库存价值控制']);a.invert_yaxis();a.set_xlim(0,2300);a.set_xlabel('334天费用 / 万元');panel(a,'a','费用构成')
for i,x in enumerate(tot):a.text(x+20,i,f'{x:.2f}',va='center',fontsize=7.5)
sv=-np.diff(tot);b.hlines(np.arange(1,4),0,sv,color=C['base']);b.scatter(sv,np.arange(1,4),color=C['soc'],s=25);b.set_ylim(3.5,-.5);b.set_yticks([]);b.set_xlim(0,600);b.set_xlabel('节省 / 万元');panel(b,'b','逐项节省')
for i,x in enumerate(sv):b.text(x+15,i+1,f'{x:.2f}',va='center',fontsize=8)
leg(f,*a.get_legend_handles_labels(),2);save(f,'q2_cost',['q2_cost'])

f,aa=fig(8.07339);a=aa[0,0];f.subplots_adjust(top=.81,bottom=.16);a.plot(h,D['q3_pv_actual']*1000,color=C['actual'],label='实际光伏',lw=1.25)
for i,style in enumerate(['--',':','-.',(0,(5,2,1,2))]):a.plot(h[i*36:],D['q3_pv_issued'][i,i*36:]*1000,color=[C['base'],C['forecast'],C['grid'],'#3C5268'][i],ls=style,label=f'{i*6:02d}:00 预报')
for x in [6,12,18]:a.axvline(x,color=C['line'],lw=.6,zorder=0)
a.set_ylim(0,12000);a.set_ylabel('光伏功率 / kW');time(a);leg(f,*a.get_legend_handles_labels(),3);save(f,'q3_forecasts',['q3_pv_actual','q3_pv_issued'])

f,aa=fig(7.2,1,2,gridspec_kw={'width_ratios':[2.4,1]});f.subplots_adjust(left=.1,wspace=.6);a,b=aa[0];a.grid(False)
a.pcolormesh(np.arange(9)-.5,np.arange(4)-.5,D['q3_validation'],cmap=LinearSegmentedColormap.from_list('cost',['#F7F9FA','#9BB5C8']),shading='flat');a.invert_yaxis();a.set_xticks(range(8),['无','6','12','6+12','18','6+18','12+18','全部'],rotation=40,ha='right');a.set_yticks(range(3),['0','50%','70%']);a.set_ylabel('误差余量分位数');a.set_xlabel('日内预报组合 / h');panel(a,'a','验证费用 / 万元')
for i in range(3):
 for j in range(8):a.text(j,i,f'{D["q3_validation"][i,j]:.1f}',ha='center',va='center',fontsize=7.3)
a.add_patch(Rectangle((6.5,.5),1,1,fill=False,ec=C['actual'],lw=1));b.plot(range(4),D['q3_validation'][1,[0,1,3,7]],'o-',color=C['grid'],mfc='white',ms=4);b.set_xticks(range(4),['0','+6','+12','+18']);b.set_xlabel('新增预报时刻 / h');b.set_ylabel('验证费用 / 万元');panel(b,'b','逐次更新');save(f,'q3_validation',['q3_validation'])

f,aa=fig(9.4,1,2,gridspec_kw={'width_ratios':[1.5,1]});f.subplots_adjust(left=.19,wspace=.8,bottom=.18);a,b=aa[0];order=[0,1,2,4,3,5,6,7];v=D['q3_cost'][0]-D['q3_cost'][order]
a.hlines(range(8),0,v,color=C['base']);a.scatter(v,range(8),color=C['grid'],s=24);a.set_yticks(range(8),['仅午夜','+06点','+12点','+18点','+06、12点','+06、18点','+12、18点','全部更新']);a.invert_yaxis();a.set_xlim(0,195);a.set_xlabel('相对仅午夜节省 / 万元');panel(a,'a','预报组合收益')
for i,x in enumerate(v):a.text(x+4,i,f'{x:.2f}',va='center',fontsize=7.6)
b.scatter(D['q3_evolution'],range(3),color=C['soc'],s=28);b.set_yticks(range(3),['基础滚动','负载修正','库存控制']);b.set_ylim(2.8,-.6);b.set_xlim(1346,1360);b.set_xlabel('334天费用 / 万元');panel(b,'b','最终策略费用')
for i,x in enumerate(D['q3_evolution']):b.text(x,i-.22,f'{x:.2f}',ha='center',fontsize=8)
save(f,'q3_updates',['q3_cost','q3_evolution'])

f,aa=fig(9,2,1,gridspec_kw={'height_ratios':[1.3,1]});f.subplots_adjust(top=.91,bottom=.13,hspace=.6);a,b=aa[:,0];a.grid(False)
im=a.imshow(D['price'],aspect='auto',origin='lower',extent=[0,24,1,365],cmap=LinearSegmentedColormap.from_list('price',['#F7F9FA','#AAC1D3','#4F6D8A','#30353B']),vmin=0,vmax=1.8);a.set_ylabel('年内日序');a.set_xlabel('时刻 / h');a.set_xticks(range(0,25,6));panel(a,'a','全年实际电价');cb=f.colorbar(im,ax=a,pad=.02,fraction=.025);cb.set_label('元/kWh')
lengths=[31,28,31,30,31,30,31,31,30,31,30,31];starts=np.r_[0,np.cumsum(lengths)];means=[];lo=[];hi=[]
for i in range(12):v=D['price'][starts[i]:starts[i+1]].ravel();means.append(v.mean());lo.append(np.quantile(v,.1,method='hazen'));hi.append(np.quantile(v,.9,method='hazen'))
b.fill_between(range(1,13),lo,hi,color=C['forecast'],alpha=.17,label='10—90%分位范围');b.plot(range(1,13),means,'o-',color=C['actual'],ms=3,label='月均值');b.set_xticks(range(1,13));b.set_xlabel('月份');b.set_ylabel('电价 / 元/kWh');panel(b,'b','月度价格分布');b.legend(loc='upper right',ncol=2);save(f,'annual_price',['price'])

f,aa=fig(10.4,2,2);f.subplots_adjust(top=.84,bottom=.12,hspace=.55)
for i,a in enumerate(aa.flat):
 a.fill_between(h,D['specified_lower'][i],D['specified_upper'][i],color=C['forecast'],alpha=.18,label='历史残差范围');a.plot(h,D['specified_price'][i],color=C['actual'],label='实际价格');a.plot(h,D['specified_forecast'][i],'--',color=C['forecast'],label='午夜预测');a.set_ylim(0,1.9);a.set_ylabel('电价 / 元/kWh');time(a,i>=2);panel(a,chr(97+i),dates[i])
leg(f,*aa[0,0].get_legend_handles_labels(),3);save(f,'price_uncertainty',['specified_lower','specified_upper','specified_price','specified_forecast'])

f,aa=fig(12.3,3,4,sharex=True,sharey='row');f.subplots_adjust(left=.12,right=.98,top=.86,bottom=.1,hspace=.32,wspace=.19)
for i in range(4):
 for j in range(3):
  a=aa[j,i]
  if j==0:
   a.plot(h,D['specified_price'][i],color=C['actual']);a.plot(h,D['specified_forecast'][i],'--',color=C['forecast']);a.set_ylim(0,1.9);panel(a,chr(97+i),dates[i])
  elif j==1:
   for k,style,color in [('dayahead','--',C['base']),('rolling','-',C['soc'])]:a.plot(h,D[k+'_soc_start_kwh'][i]/1000,style,color=color)
   a.set_ylim(0,12);a.set_yticks([1.2,6,10.8])
  else:
   for k,style,color in [('dayahead','--',C['base']),('rolling','-',C['emergency'])]:a.step(e,np.r_[0,np.cumsum(np.maximum(D[k+'_emergency_kwh'][i],0))],where='post',ls=style,color=color)
   a.set_ylim(0,260)
  time(a,j==2);a.set_xticks([0,12,24])
  for x in [6,12,18]:a.axvline(x,color=C['line'],lw=.5,ls=':')
for a,label in zip(aa[:,0],['电价 / 元/kWh','储电量 / MWh','累计紧急购电 / kWh']):a.set_ylabel(label)
from matplotlib.lines import Line2D
leg(f,[Line2D([],[],color=C['actual']),Line2D([],[],color=C['forecast'],ls='--'),Line2D([],[],color=C['base'],ls='--'),Line2D([],[],color=C['soc'])],['实际电价','午夜预测','日前策略','滚动策略（下两行）'],2)
save(f,'price_dispatch',['specified_price','specified_forecast','dayahead_soc_start_kwh','rolling_soc_start_kwh','dayahead_emergency_kwh','rolling_emergency_kwh'])

f,aa=fig(9,2,2,gridspec_kw={'width_ratios':[2.3,1]});f.subplots_adjust(left=.12,wspace=.44,top=.89,bottom=.14,hspace=.6)
for i in range(2):
 a,b=aa[i];v=D['q4_month_savings'][i]*10;a.vlines(range(2,13),0,v,color=C['base'],lw=1);a.scatter(range(2,13),v,color=C['soc'],s=20);a.set_ylim(0,28 if i==0 else 2.8);a.set_xticks(range(2,13,2));a.set_ylabel('月度节省 / 千元');panel(a,'ac'[i],['日前：月度分布','滚动：月度分布'][i]);
 if i==1:a.set_xlabel('月份')
 ci=D['q4_ci'][i]*10;mu=D['q4_savings'][i]*10;b.errorbar(mu,1,xerr=[[mu-ci[0]],[ci[1]-mu]],fmt='o',color=C['soc'],capsize=3,ms=4);b.text(mu,1.14,f'{mu:.2f}',ha='center');b.set_ylim(.7,1.5);b.set_yticks([]);b.set_xlim(0,210 if i==0 else 12);b.grid(axis='x');panel(b,'bd'[i],'全期与95%区间');b.set_xlabel('全期节省 / 千元')
save(f,'inventory_savings',['q4_month_savings','q4_savings','q4_ci'])
(ROOT/'artifacts/v9/figure_manifest.json').write_text(json.dumps(dict(backend='Python Matplotlib',source_sha256=hashlib.sha256((ROOT/'artifacts/v8/figure_data.mat').read_bytes()).hexdigest(),figures=manifest),ensure_ascii=False,indent=2),encoding='utf-8')
