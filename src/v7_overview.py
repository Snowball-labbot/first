"""Publication-size vector overview of the actual V3/V4 modeling pipeline."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]

def main():
    out=ROOT/'figures/v7';out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':8.2,'svg.fonttype':'none','pdf.fonttype':42})
    fig,ax=plt.subplots(figsize=(6.15,5.15));fig.subplots_adjust(0,0,1,1)
    ax.set(xlim=(0,16),ylim=(0,13.4));ax.axis('off')
    ink='#26374B';line='#81909D';blue='#4D779B';purple='#8074C8'
    text_boxes=[]
    def box(x,y,w,h,text,color=blue,fill='#F4F7FA',size=8.2,bold=False):
        patch=FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.035,rounding_size=0.08',linewidth=.75,edgecolor=color,facecolor=fill)
        ax.add_patch(patch)
        t=ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=size,color=ink,weight='bold' if bold else 'normal',linespacing=1.5)
        text_boxes.append((patch,t))
    def arrow(a,b):
        ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=8,linewidth=.75,color=line,shrinkA=1,shrinkB=1))
    xs=[.3,4.25,8.2,12.15];w=3.55;cs=[x+w/2 for x in xs]
    data=['附件1\n分时电价、单日供需','附件2\n全年负载与光伏','附件3\n四时刻光伏预报','附件4\n全年波动电价']
    for x,t in zip(xs,data):box(x,11.7,w,1.08,t,size=8)
    box(.3,10.25,15.4,.83,'时间与单位对齐  →  按发布时间构造可用信息集',fill='white',bold=True)
    for c in cs:arrow((c,11.65),(c,11.12))
    arrow((8,10.18),(8,9.83))
    box(.3,8.6,15.4,1.15,'共同物理模型\n能量平衡 · 储电量递推 · 容量与功率约束 · 充放电互斥',fill='#EEF2F8',bold=True)
    for c in cs:arrow((c,8.54),(c,7.99))
    titles=['问题一｜确定性调度','问题二｜供需风险','问题三｜日内修正','问题四｜价格波动']
    methods=['多期线性规划\n连续库存价值\n首末状态闭合',
             '岭回归与风险校准\n历史配对残差\n库存价值控制',
             '滚动计划与负载修正\n新增／取消分项结算\n计入未来调单机会',
             '同期／岭回归／GRU\n分别接入日前与滚动\n未来价格预测']
    for i,x in enumerate(xs):
        box(x,7.18,w,.74,titles[i],color=purple if i==3 else blue,fill='#ECEAF6' if i==3 else '#E8EFF5',size=8,bold=True)
        box(x,4.66,w,2.39,methods[i],color=purple if i==3 else blue,fill='white',size=8)
        if i<3:arrow((x+w+.03,7.55),(xs[i+1]-.03,7.55))
        arrow((x+w/2,4.60),(x+w/2,4.10))
    outputs=['单日最优购电计划\n储能收益与效率检验',
             '334天日前策略\n风险余量节费效果',
             '334天滚动策略\n日内预报净经济价值',
             '两类策略与预测对照\n价格改进空间']
    for x,t in zip(xs,outputs):box(x,2.72,w,1.30,t,fill='#F6F6F8',size=7.9)
    for c in cs:arrow((c,2.66),(c,2.14))
    box(.3,.78,15.4,1.27,'模型评价与推广\n库存边际价值 · 放电择时 · 储能容量配置',fill='#F4F6F7',bold=True)
    fig.canvas.draw();renderer=fig.canvas.get_renderer();issues=[]
    for i,(patch,text) in enumerate(text_boxes):
        a=patch.get_window_extent(renderer);b=text.get_window_extent(renderer)
        if not (a.x0<=b.x0 and a.x1>=b.x1 and a.y0<=b.y0 and a.y1>=b.y1):issues.append(i)
    assert not issues,issues
    for ext in ['png','svg','pdf']:fig.savefig(out/f'modeling_overview.{ext}',dpi=320,facecolor='white')
    vector=out/'modeling_overview.svg'
    vector.write_text('\n'.join(line.rstrip() for line in vector.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')
    plt.close(fig)
    with Image.open(out/'modeling_overview.png') as im:im.convert('L').save(out/'modeling_overview_grayscale.png')
    (ROOT/'artifacts/v7/overview_audit.json').write_text(json.dumps({'type':'conceptual flowchart; no synthetic data','text_boxes':len(text_boxes),'overflow_boxes':issues,'size_inches':[6.15,5.15],'png_dpi':320},ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'modeling_overview.mmd').write_text('''flowchart TB
    A[附件1—4：供需、预报、电价] --> B[时间单位对齐与信息集构造]
    B --> C[能量平衡、储能递推、容量功率与互斥约束]
    C --> Q1[问题一：多期线性规划与连续库存价值]
    C --> Q2[问题二：风险校准与库存价值控制]
    C --> Q3[问题三：滚动计划与未来调单机会]
    C --> Q4[问题四：价格预测接入日前与滚动调度]
    Q1 --> Q2 --> Q3 --> Q4
    Q1 --> R[模型评价与推广：库存边际价值、放电择时、容量配置]
    Q2 --> R
    Q3 --> R
    Q4 --> R
''',encoding='utf-8')
    print('Overview exported: PNG, SVG, PDF, grayscale, Mermaid')

if __name__=='__main__':main()
