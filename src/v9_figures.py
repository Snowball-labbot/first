"""V9 rebuild: frozen V8 evidence; V7 restoration; guide-derived visual hierarchy."""
from pathlib import Path
import json,hashlib,argparse
import numpy as np
from scipy.io import loadmat
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle,Polygon,Circle,FancyArrowPatch
from matplotlib.colors import ListedColormap,BoundaryNorm,to_rgb,to_hex
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'figures/v9';OUT.mkdir(parents=True,exist_ok=True)
D=loadmat(ROOT/'artifacts/v8/figure_data.mat',squeeze_me=True)
C=dict(actual='#E0461F',price='#E0461F',grid='#0D5FD1',forecast='#0D5FD1',load='#295D74',pv='#F3AC1B',soc='#9391E8',emergency='#7A261B',base='#7599A8',ink='#262626',line='#E4E8EB')
OLD=dict(grid='#4D779B',soc='#8074C8',load='#3E608D',pv='#C58A26',charge='#7AB656',discharge='#EF8B67',price='#8D2F25',actual='#CD3B42',forecast='#7895C1')
plt.rcParams.update({'font.family':['Arial','Microsoft YaHei'],'font.size':9,'axes.labelsize':10,'axes.titlesize':10,'xtick.labelsize':9,'ytick.labelsize':9,'legend.fontsize':9,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.65,'axes.edgecolor':C['ink'],'axes.labelcolor':C['ink'],'text.color':C['ink'],'xtick.color':C['ink'],'ytick.color':C['ink'],'xtick.major.size':3,'ytick.major.size':3,'lines.linewidth':1.35,'svg.fonttype':'none','pdf.fonttype':42,'axes.unicode_minus':False,'legend.frameon':False,'savefig.facecolor':'white'})
h=D['hours'];edges=np.arange(145)/6;dates=['2025-03-20','2025-06-21','2025-09-23','2025-12-21'];manifest=[]
def pale(c,f=.83):return to_hex(np.array(to_rgb(c))*(1-f)+f)
def fig(cm):return plt.figure(figsize=(15.5/2.54,cm/2.54),facecolor='white')
def ax(f,rect):
 a=f.add_axes(rect);a.set_axisbelow(True);return a
def grid(a):a.grid(axis='y',color=C['line'],lw=.5)
def panel(a,k,title):a.text(-.02,1.07,f'({k})',transform=a.transAxes,fontweight='bold',fontsize=11,va='bottom');a.set_title(title,loc='center',pad=9,fontweight='normal')
def step(a,v,**kw):return a.stairs(v,edges,baseline=0 if kw.get('fill') else None,**kw)
def time(a,label=True,ticks=range(0,25,6)):
 a.set_xlim(0,24);a.set_xticks(list(ticks))
 if label:a.set_xlabel('时刻 / h')
 else:a.tick_params(labelbottom=False)
def legend(f,handles,labels,n=3,y=.985):return f.legend(handles,labels,loc='upper center',bbox_to_anchor=(.54,y),ncol=n,handlelength=2.2,columnspacing=1.2)
def save(f,name,keys):
 f.canvas.draw();renderer=f.canvas.get_renderer();outside=[]
 for t in f.findobj(matplotlib.text.Text):
  if not t.get_visible() or not t.get_text():continue
  bb=t.get_window_extent(renderer);fb=f.bbox
  if bb.x0<fb.x0-1 or bb.y0<fb.y0-1 or bb.x1>fb.x1+1 or bb.y1>fb.y1+1:outside.append(t.get_text())
 f.savefig(OUT/(name+'.svg'))
 with plt.rc_context({'svg.fonttype':'path'}):f.savefig(OUT/(name+'_word.svg'))
 f.savefig(OUT/(name+'.pdf'));f.savefig(OUT/(name+'.png'),dpi=600)
 Image.open(OUT/(name+'.png')).convert('L').save(OUT/(name+'_gray.png'))
 manifest.append(dict(name=name,width_cm=15.5,height_cm=float(f.get_figheight()*2.54),source_keys=keys,source_hashes={k:hashlib.sha256(np.asarray(D[k]).tobytes()).hexdigest() for k in keys},outside_text=outside))
 plt.close(f);print(name,'outside=',outside,flush=True)

def framework():
 f=fig(11.5);a=ax(f,[.015,.015,.97,.97]);a.axis('off');a.set_xlim(0,100);a.set_ylim(0,100)
 def t(x,y,s,size=9,ha='center',**kw):a.text(x,y,s,fontsize=size,ha=ha,va='center',**kw)
 def line(xs,ys,col=C['ink'],lw=1):a.plot(xs,ys,color=col,lw=lw)
 def arrow(x,y,xx,yy,col=C['ink']):a.add_patch(FancyArrowPatch((x,y),(xx,yy),arrowstyle='-|>',mutation_scale=8,lw=.9,color=col))
 t(1,97,'(a)',11,'left',fontweight='bold');t(24,97,'微网物理系统',10,fontweight='bold');t(53,97,'(b)',11,'left',fontweight='bold');t(79,97,'共同决策过程',10,fontweight='bold')
 line([4,8,12],[76,89,76],OLD['grid']);line([5.5,10.5],[81,81],OLD['grid']);line([4.5,11.5],[85,85],OLD['grid']);line([5.5,10.5,6.8,9.3],[81,85,85,81],OLD['grid'],.65);t(8,72,'外部电网',8.5)
 a.add_patch(Polygon([(21,86),(31,86),(29,92),(23,92)],fc=pale(C['pv']),ec=OLD['pv'],lw=.8))
 for x in [24,27]:line([x,x+.6],[86,92],OLD['pv'],.5)
 line([22,30],[89,89],OLD['pv'],.5);line([26,26],[86,84],OLD['pv']);t(26,80,'光伏出力',8.5)
 for x,ht in [(38,8),(42,11),(46,6)]:
  a.add_patch(Rectangle((x,77),3,ht,fc=pale(C['load']),ec=C['load'],lw=.7))
  for y in np.arange(79,77+ht,2.5):a.add_patch(Rectangle((x+.8,y),.7,.8,fc=C['load'],ec='none'))
 t(43,72,'小区负载',8.5);line([14,36],[67,67],C['grid'],1.2);line([4,0,0],[76,76,67],C['grid']);arrow(0,67,18,67,C['grid']);arrow(26,78,26,67,OLD['pv']);line([34,51,51],[67,67,82],C['load']);arrow(51,82,49,82,C['load'])
 a.add_patch(Rectangle((20,52),12,6,fc=pale(C['soc']),ec=OLD['soc'],lw=.9));a.add_patch(Rectangle((32,54),1,2,fc=OLD['soc'],ec='none'))
 for x in [22,25,28]:a.add_patch(Rectangle((x,53.3),2,3.4,fc=OLD['soc'],ec='none',alpha=.65))
 arrow(23,66,23,60,OLD['charge']);arrow(29,60,29,66,OLD['discharge']);t(26,48,'储能状态 SOC',8.5);t(26,42,'能量平衡 · 功率边界 · 容量约束',8.5)
 for y,title,sub,col in [(85,'预测供需与价格','决策时已知的历史信息',C['forecast']),(71,'计划与合同修订','线性规划 / 滚动优化',C['grid']),(57,'实时储能与补购','库存价值控制',C['soc'])]:
  a.add_patch(Rectangle((58,y-5),36,10,fc=pale(col,.93),ec='none'));line([58,58],[y-5,y+5],col,1.5);t(76,y+1.8,title,9.5);t(76,y-2.2,sub,8.2)
 arrow(76,79,76,77,C['base']);arrow(76,65,76,63,C['base']);line([95,98,98,95],[57,57,85,85],C['base'],.7);arrow(98,85,94,85,C['base']);t(76,42,'合同结算与紧急补购总费用',8.5)
 line([1,99],[36,36],C['line'],.7);t(1,32,'(c)',11,'left',fontweight='bold');t(51,32,'四问沿信息与调整权限逐层扩展',10)
 qcols=[12,37,62,87];qs=[('问题一','确定性输入','联合购电与储能'),('问题二','供需不确定性','日前固定合同'),('问题三','日内预报更新','非对称结算调单'),('问题四','波动电价','日前 / 滚动双分支')]
 for x,(q,s,ss) in zip(qcols,qs):a.add_patch(Circle((x,23),1.2,fc=C['grid'],ec='white',lw=.6));t(x,17,q,9.5,fontweight='bold');t(x,11,s,8.8);t(x,6,ss,8.5)
 for x,y in zip(qcols[:-1],qcols[1:]):arrow(x+2,23,y-2,23,C['grid'])
 save(f,'modeling_overview',[])

def restore():
 with plt.rc_context({'font.family':['Microsoft YaHei'],'font.size':9,'axes.labelsize':9,'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8}):
  f=fig(11.39172);aa=f.subplots(3,1,sharex=True,gridspec_kw={'height_ratios':[1.8,1,.7]});f.subplots_adjust(left=.105,right=.985,top=.90,bottom=.11,hspace=.13);a,b,c=aa
  step(a,D['q1_charge_kwh']*6,fill=True,color=OLD['charge'],alpha=.42,label='充电');step(a,-D['q1_discharge_kwh']*6,fill=True,color=OLD['discharge'],alpha=.6,label='放电');step(a,D['q1_plan_kwh']*6,color=OLD['grid'],lw=1.15,label='外网购电');step(a,D['q1_load_kwh']*6,color=OLD['load'],ls='--',lw=.8,label='负载');step(a,D['q1_pv_kwh']*6,color=OLD['pv'],lw=.8,label='光伏');a.set_ylabel('功率 / kW');a.legend(ncol=5,loc='lower left',bbox_to_anchor=(0,1.01),columnspacing=1,handlelength=2)
  s=np.r_[D['q1_soc_start_kwh'][0],D['q1_soc_end_kwh']];b.plot(edges,s,color=OLD['soc'],lw=1.4);b.fill_between(edges,1200,s,color=OLD['soc'],alpha=.1)
  for y in [1200,10800]:b.axhline(y,color=OLD['soc'],ls='--',lw=.65)
  b.set(ylim=(500,11800),yticks=[1200,6000,10800],ylabel='储电量 / kWh');step(c,D['q1_price'],color=OLD['price'],lw=1.1);c.set_ylabel('电价\n元/kWh');time(c,ticks=range(0,25,4))
  for i,a in enumerate(aa):grid(a);a.text(.01,.92,f'({chr(97+i)})',transform=a.transAxes,va='top',fontsize=8)
  save(f,'result_q1_dispatch',['q1_charge_kwh','q1_discharge_kwh','q1_plan_kwh','q1_load_kwh','q1_pv_kwh','q1_soc_start_kwh','q1_soc_end_kwh','q1_price'])
  f=fig(16.368);aa=f.subplots(4,2,sharex=True,sharey='col');f.subplots_adjust(left=.10,right=.985,top=.955,bottom=.075,hspace=.30,wspace=.29)
  for j,key in enumerate(['load','pv']):
   obs=D['q2_'+key+'_kwh'];pred=D['q2_forecast_'+key+'_kwh'];upper=max(obs.max(),pred.max())*6*1.22
   for i in range(4):
    a=aa[i,j];a.plot(h,obs[i]*6,color=OLD['actual'],lw=1.05,label='实际');a.plot(h,pred[i]*6,color=OLD['forecast'],lw=1.2,ls='--',label='预测');a.set_title(dates[i],loc='left',fontsize=8.5,pad=7);a.set_ylim(0,upper);a.set_ylabel(('负载' if j==0 else '光伏')+' / kW',fontsize=8);grid(a);time(a,i==3)
  aa[0,0].legend(loc='upper right',ncol=2,fontsize=7.5,handlelength=2)
  save(f,'q2_forecasts',['q2_load_kwh','q2_forecast_load_kwh','q2_pv_kwh','q2_forecast_pv_kwh'])
  f=fig(8.07339);a=ax(f,[.10,.16,.875,.81]);a.spines[['top','right']].set_visible(True);a.plot(h,D['q3_pv_actual']*1000,color=OLD['actual'],lw=1.4,label='实际光伏')
  for i,col in enumerate(['#9D9EA3','#7895C1','#3E608D','#8074C8']):a.plot(h[i*36:],D['q3_pv_issued'][i,i*36:]*1000,color=col,ls='--',lw=1.05,label=f'{i*6:02d}:00 预报')
  a.set_ylim(0,12000);a.set_ylabel('光伏功率 / kW');time(a,ticks=[0,5,10,15,20]);a.legend(ncol=3,loc='upper center');grid(a);save(f,'q3_forecasts',['q3_pv_actual','q3_pv_issued'])

def inputs():
 f=fig(7.9);a=ax(f,[.115,.43,.86,.47]);b=ax(f,[.115,.15,.86,.18]);step(a,D['q1_pv_kwh']*6,fill=True,color=pale(C['pv'],.68),label='光伏');step(a,D['q1_load_kwh']*6,color=C['load'],label='负载');a.set_ylabel('功率 / kW');time(a,False);grid(a);panel(a,'a','供需曲线');a.legend(ncol=2,loc='upper left');step(b,D['q1_price'],color=C['price']);b.set_ylabel('电价\n元/kWh');time(b);grid(b);panel(b,'b','分时电价');save(f,'raw_q1_inputs',['q1_load_kwh','q1_pv_kwh','q1_price'])

def efficiency():
 f=fig(7.8);a=ax(f,[.145,.21,.38,.63]);b=ax(f,[.70,.21,.275,.63]);v=D['q1_waterfall'][[0,2,1]]
 a.barh(range(3),v,.48,color=[pale(C['base']),pale(C['soc']),pale(C['grid'])],edgecolor=[C['base'],C['soc'],C['grid']],lw=.8);a.set_yticks(range(3),['无储能','实际效率','无损储能']);a.invert_yaxis();a.set_xlim(0,5.25);a.set_xlabel('日费用 / 万元');panel(a,'a','储能费用');a.grid(axis='x',color=C['line'],lw=.5)
 for i,x in enumerate(v):a.text(.15,i,f'{x*10000:,.2f}',va='center',fontsize=9)
 a.text(.97,1.01,'标注：元',transform=a.transAxes,ha='right',fontsize=8.5)
 b.plot(D['q1_efficiency'],D['q1_sensitivity'],'o-',color=C['grid'],mfc='white',ms=4);b.scatter([81],[D['q1_sensitivity'][2]],s=65,facecolors='none',edgecolors=C['ink'],zorder=5);b.set_xticks([64,81,100]);b.set_ylim(3.15,3.95);b.set_xlabel('往返效率 / %');b.set_ylabel('日费用 / 万元');panel(b,'b','效率响应');grid(b);save(f,'q1_efficiency',['q1_waterfall','q1_efficiency','q1_sensitivity'])

def validation():
 f=fig(8);aa=[ax(f,[.115,.23,.365,.60]),ax(f,[.615,.23,.365,.60])]
 for j,key in enumerate(['validation_cost','validation_emergency']):
  a=aa[j]
  for k,(label,col,marker) in enumerate([('同期预测',C['base'],'s'),('岭回归',C['grid'],'o')]):a.plot(range(4),D[key][k],marker=marker,color=col,ls='--' if k==0 else '-',mfc='white',ms=4.2,label=label)
  a.set_xticks(range(4),['无余量','70%','80%','90%']);a.set_xlabel('误差余量分位数');a.set_ylabel('验证费用 / 万元');grid(a);panel(a,'ab'[j],['总费用','紧急购电费'][j])
 aa[0].scatter([1],[D['validation_cost'][1,1]],s=70,facecolors='none',edgecolors=C['ink'],zorder=5);aa[0].annotate('50.98',xy=(1,D['validation_cost'][1,1]),xytext=(1.5,54.2),fontsize=8.5,arrowprops={'arrowstyle':'-','color':C['ink'],'lw':.6});legend(f,*aa[0].get_legend_handles_labels(),n=2);save(f,'q2_validation',['validation_cost','validation_emergency'])

def cost():
 f=fig(10.4);a=ax(f,[.12,.52,.86,.36]);b=ax(f,[.23,.105,.75,.22]);val=D['q2_cost'][[0,1,3,4]];tot=val.sum(1);sv=-np.diff(tot);starts=[0,tot[1],tot[2],tot[3],0];heights=[tot[0],*sv,tot[3]]
 for i,(bt,ht) in enumerate(zip(starts,heights)):
  col=C['base'] if i==0 else C['soc'] if i==4 else C['grid'];a.bar(i,ht,bottom=bt,width=.52,color=pale(col,.75),edgecolor=col,lw=.8);label=f'{ht:,.2f}' if i in [0,4] else f'−{ht:.2f}';a.text(i,bt+ht+50,label,ha='center',fontsize=8.5)
 for i,y in enumerate(tot):a.plot([i+.26,i+.74],[y,y],ls='--',color=C['base'],lw=.65)
 a.set_ylim(0,2250);a.set_xlim(-.6,4.6);a.set_xticks(range(5),['同期基线','岭回归','70%余量','库存控制','最终费用']);a.set_ylabel('334天费用 / 万元');grid(a);panel(a,'a','逐项改进的费用变化')
 for i in range(4):b.plot([val[i,0],tot[i]],[i,i],color=pale(C['emergency'],.35),lw=2);b.scatter(val[i,0],i,color=C['grid'],s=22,zorder=3);b.scatter(tot[i],i,color=C['emergency'],marker='s',s=20,zorder=3)
 b.set_yticks(range(4),['同期无余量','岭回归无余量','岭回归70%余量','库存价值控制']);b.invert_yaxis();b.set_xlim(800,2100);b.set_xticks([800,1200,1600,2000]);b.set_xlabel('普通计划费 → 含紧急费的总费用 / 万元');panel(b,'b','支出构成');b.grid(axis='x',color=C['line'],lw=.5);save(f,'q2_cost',['q2_cost'])

def q3validation():
 f=fig(8.6);a=ax(f,[.10,.29,.57,.52]);b=ax(f,[.81,.29,.17,.52]);bounds=[49,50,52,55,57];cols=['#EEF3F7','#C1D7F3','#7599A8','#295D74'];norm=BoundaryNorm(bounds,len(cols));im=a.pcolormesh(np.arange(9)-.5,np.arange(4)-.5,D['q3_validation'],cmap=ListedColormap(cols),norm=norm,edgecolors='white',lw=.8);a.invert_yaxis();a.set_xticks(range(8),['无','6','12','6+12','18','6+18','12+18','全部'],fontsize=8.5,rotation=35,ha='right');a.set_yticks(range(3),['0','50%','70%']);a.set_ylabel('误差余量');panel(a,'a','一月验证费用 / 万元')
 for i in range(3):
  for j in range(8):a.text(j,i,f'{D["q3_validation"][i,j]:.1f}',ha='center',va='center',fontsize=8.5,color='white' if D['q3_validation'][i,j]>=55 else C['ink'])
 a.add_patch(Rectangle((6.5,.5),1,1,fill=False,ec=C['ink'],lw=1.2));a.set_xlabel('日内预报组合 / h');cax=ax(f,[.13,.085,.49,.033]);cb=f.colorbar(im,cax=cax,orientation='horizontal',ticks=bounds);cb.outline.set_linewidth(.5)
 b.plot(range(4),D['q3_validation'][1,[0,1,3,7]],'o-',color=C['grid'],mfc='white',ms=4);b.set_xticks(range(4),['0','+6','+12','+18'],rotation=45);b.set_ylabel('验证费用 / 万元');panel(b,'b','逐次更新');grid(b);save(f,'q3_validation',['q3_validation'])

def updates():
 f=fig(10);a=ax(f,[.12,.42,.53,.43]);m=ax(f,[.12,.14,.53,.18]);b=ax(f,[.80,.25,.18,.60]);order=np.array([0,1,2,4,3,5,6,7]);v=D['q3_cost'][0]-D['q3_cost'][order]
 a.vlines(range(8),0,v,color=pale(C['grid'],.60),lw=2);a.scatter(range(8),v,s=29,color=C['grid'],edgecolor='white',lw=.7);a.set_ylim(0,175);a.set_xlim(-.5,7.5);a.set_xticks([]);a.set_ylabel('相对仅午夜节省 / 万元');grid(a);panel(a,'a','预报组合收益')
 for i,x in enumerate(v):a.text(i,x+7,f'{x:.1f}',ha='center',fontsize=8.5)
 for j,mask in enumerate(order):
  on=[i for i in range(3) if mask & 1<<i];m.scatter([j]*3,range(3),s=19,color='#E4E8EB')
  if len(on)>1:m.plot([j,j],[min(on),max(on)],color=C['grid'],lw=1)
  m.scatter([j]*len(on),on,s=24,color=C['grid'])
 m.set_xlim(-.5,7.5);m.set_ylim(2.5,-.5);m.set_yticks(range(3),['06点','12点','18点']);m.set_xticks([]);m.spines[:].set_visible(False);m.tick_params(length=0);m.set_xlabel('实心点表示启用该次预报',labelpad=8,fontsize=9)
 b.plot(D['q3_evolution'],range(3),'o',color=C['soc'],ms=5);b.set_xlim(1345,1361);b.set_xticks([1350,1360]);b.set_ylim(2.6,-.6);b.set_yticks(range(3),['基础滚动','负载修正','库存控制'],fontsize=8.5);b.set_xlabel('全期费用\n万元');panel(b,'b','最终策略')
 for i,x in enumerate(D['q3_evolution']):b.text(1353,i-.22,f'{x:.2f}',ha='center',fontsize=8.5)
 save(f,'q3_updates',['q3_cost','q3_evolution'])

def annual():
 f=fig(9.9);a=ax(f,[.10,.47,.77,.40]);b=ax(f,[.10,.13,.77,.21]);bounds=[0,.3,.6,.9,1.2,1.5,1.8];cols=['#FBF6F0','#F2DBCE','#E2B49E','#ED7D60','#E0461F','#7A261B'];im=a.imshow(D['price'].T,extent=[0,365,0,24],origin='lower',aspect='auto',cmap=ListedColormap(cols),norm=BoundaryNorm(bounds,len(cols)),interpolation='none')
 starts=np.r_[0,np.cumsum([31,28,31,30,31,30,31,31,30,31,30,31])];a.set_xticks(starts[:-1]+15,[str(i) for i in range(1,13)]);a.set_yticks([0,6,12,18,24]);a.set_ylabel('时刻 / h');panel(a,'a','全年十分钟实际电价');ca=ax(f,[.91,.47,.020,.40]);cb=f.colorbar(im,cax=ca,ticks=bounds);cb.outline.set_linewidth(.5);ca.set_title('元/kWh',fontsize=9,pad=9)
 means=[];lo=[];hi=[]
 for i in range(12):v=D['price'][starts[i]:starts[i+1]].ravel();means.append(v.mean());lo.append(np.quantile(v,.1,method='hazen'));hi.append(np.quantile(v,.9,method='hazen'))
 means=np.array(means);b.errorbar(range(1,13),means,yerr=[means-lo,hi-means],fmt='o',color=C['price'],ms=4,capsize=3,elinewidth=1);b.set_xlim(.5,12.5);b.set_ylim(0,1.85);b.set_xticks(range(1,13));b.set_ylabel('电价 / 元/kWh');b.set_xlabel('月份');grid(b);panel(b,'b','月均值与10%—90%分位范围');save(f,'annual_price',['price'])

def uncertainty():
 f=fig(10.7);aa=[]
 for i in range(4):
  a=ax(f,[.115+(i%2)*.49,.59-(i//2)*.42,.37,.27]);aa.append(a);a.fill_between(h,D['specified_lower'][i],D['specified_upper'][i],color=pale(C['forecast'],.86),lw=0,label='历史残差范围');a.plot(h,D['specified_price'][i],color=C['actual'],label='实际价格',lw=1.1);a.plot(h,D['specified_forecast'][i],ls='--',color=C['forecast'],label='午夜预测',lw=1.2);a.set_ylim(0,1.9);a.set_yticks([0,.6,1.2,1.8]);a.set_ylabel('电价 / 元/kWh');time(a,i>=2);grid(a);panel(a,'abcd'[i],dates[i])
 legend(f,*aa[0].get_legend_handles_labels(),n=3,y=.995);save(f,'price_uncertainty',['specified_lower','specified_upper','specified_price','specified_forecast'])

def dispatch():
 f=fig(12)
 for r in range(3):
  for i in range(4):
   a=ax(f,[.12+i*.225,.69-r*.265,.175,.185])
   if r==0:a.plot(h,D['specified_price'][i],color=C['actual'],lw=1);a.plot(h,D['specified_forecast'][i],ls='--',color=C['forecast'],lw=1);a.set_ylim(0,1.9);a.set_yticks([0,.8,1.6]);a.set_title(dates[i][5:],fontsize=10,pad=8)
   elif r==1:
    for prefix,ls,col in [('dayahead','--',pale(C['soc'],.15)),('rolling','-', '#6865B5')]:a.plot(h,D[prefix+'_soc_start_kwh'][i]/1000,ls=ls,color=col,lw=1.05)
    a.set_ylim(0,12);a.set_yticks([1.2,6,10.8])
   else:
    for prefix,ls,col in [('dayahead','--',pale(C['emergency'],.40)),('rolling','-',C['emergency'])]:a.step(edges,np.r_[0,np.cumsum(np.maximum(D[prefix+'_emergency_kwh'][i],0))],where='post',color=col,ls=ls,lw=1.1)
    a.set_ylim(0,260);a.set_yticks([0,100,200])
   time(a,r==2,ticks=[0,12,24]);grid(a);a.tick_params(labelsize=8.5)
   for t in [6,12,18]:a.axvline(t,color='#D1D6DC',ls=':',lw=.55,zorder=0)
   if i>0:a.tick_params(labelleft=False)
   else:a.set_ylabel(['电价 / 元/kWh','储电量 / MWh','累计紧急购电 / kWh'][r],fontsize=9)
   a.text(-.04,1.04,f'({chr(97+r*4+i)})',transform=a.transAxes,fontsize=9,fontweight='bold',va='bottom')
 legend(f,[Line2D([],[],color=C['actual']),Line2D([],[],color=C['forecast'],ls='--'),Line2D([],[],color=C['ink'],ls='--'),Line2D([],[],color=C['ink'])],['实际电价','午夜预测','日前执行','滚动执行'],n=4,y=.992)
 save(f,'price_dispatch',['specified_price','specified_forecast','dayahead_soc_start_kwh','rolling_soc_start_kwh','dayahead_emergency_kwh','rolling_emergency_kwh'])

def savings():
 f=fig(9.5)
 for i in range(2):
  a=ax(f,[.12,.60-i*.43,.49,.25]);b=ax(f,[.77,.60-i*.43,.21,.25]);v=D['q4_month_savings'][i]*10;a.vlines(range(2,13),0,v,color=pale(C['soc'],.5),lw=1.5);a.scatter(range(2,13),v,s=26,color='#6865B5',edgecolor='white',lw=.5);a.set_ylim(0,28 if i==0 else 2.8);a.set_xticks(range(2,13,2));a.set_ylabel('月度节省 / 千元');grid(a);panel(a,'ac'[i],['日前策略','滚动策略'][i])
  if i==1:a.set_xlabel('月份')
  mu=D['q4_savings'][i]*10;ci=D['q4_ci'][i]*10;b.errorbar(mu,1,xerr=[[mu-ci[0]],[ci[1]-mu]],fmt='o',color='#6865B5',capsize=3,ms=5);b.text(mu,1.25,f'{mu:.2f}',ha='center',fontsize=9.5);b.set_ylim(.6,1.7);b.set_yticks([]);b.set_xlim(0,210 if i==0 else 12);b.set_xticks([0,100,200] if i==0 else [0,5,10]);b.set_xlabel('全期节省 / 千元');panel(b,'bd'[i],'95%区间')
 save(f,'inventory_savings',['q4_month_savings','q4_savings','q4_ci'])

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--only',default='');args=parser.parse_args()
 for job in [restore,framework,inputs,efficiency,validation,cost,q3validation,updates,annual,uncertainty,dispatch,savings]:
  if not args.only or job.__name__ in args.only.split(','):job()
 mf=ROOT/'artifacts/v9/figure_manifest.json'
 if args.only and mf.exists():
  old=json.loads(mf.read_text(encoding='utf8'))['figures'];names={x['name'] for x in manifest};manifest=[x for x in old if x['name'] not in names]+manifest
 mf.write_text(json.dumps(dict(edition='V9 rebuild 2026-09-13',backend='Python Matplotlib',source_sha256=hashlib.sha256((ROOT/'artifacts/v8/figure_data.mat').read_bytes()).hexdigest(),figures=manifest),ensure_ascii=False,indent=2),encoding='utf8')
