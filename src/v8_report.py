"""Revise the V7 manuscript with V6-style abstract and audited V8 evidence."""
from pathlib import Path
import json
import re
import pandas as pd
from src.deliver_q12 import blocks, md_table

ROOT=Path(__file__).resolve().parents[1]


def main():
    md=(ROOT/'reports/完整论文_V7.md').read_text(encoding='utf-8')
    q=pd.read_csv(ROOT/'artifacts/v8/q1_intervals.csv')
    s=json.loads((ROOT/'artifacts/v8/q1_summary.json').read_text())
    eff=pd.read_csv(ROOT/'artifacts/v8/q1_efficiency.csv')
    def replace_paragraph(prefix,new):
        nonlocal md
        pattern=r'^'+re.escape(prefix)+r'[^\n]*'
        assert len(re.findall(pattern,md,re.M))==1,prefix
        md=re.sub(pattern,lambda _:new,md,flags=re.M)
    abstract='''针对微网计划购电、储能运行与日内调单的耦合关系，本文以实际总购电费用最小为目标，构建“供需预测—风险校准—库存价值控制”的统一调度框架。在共同的能量平衡和储能约束下，依次扩展可用信息与合同调整权限。

针对问题一，建立**多期线性规划模型**。利用自由弃电条件下的等价变换处理充放电互斥，联合优化购电量与储能状态。最优日购电费为35,126.95元，购电59,482.70 kWh，较无储能节省26.90%，为后续各问提供物理模型与求解基础。

针对问题二，建立**岭回归预测、分位数风险校准与历史路径库存价值模型**。以70%误差余量控制欠购风险，利用过去28日配对残差估计后续缺口费用。2—12月334天总费用为13,991,392.60元；在相同计划规则及初末库存下，库存价值控制节省141,219.56元。

针对问题三，建立**非对称结算滚动优化与可调单库存价值模型**。在6、12、18点利用新预报修订合同，按历史费用逐月选择负载修正方式，并将下次调单机会纳入库存估值。334天总费用为13,479,283.32元；库存价值控制在负载修正基础上再节省9,844.62元。

针对问题四，在第二、三问基础上建立**波动电价下的日前与滚动调度模型**。以历史价格预测驱动计划及库存估值，以当前实际价格执行与结算，并用历史残差范围刻画价格不确定性。两分支334天费用分别为14,765,492.68元与14,210,881.01元，库存价值控制分别节省115,042.37元和5,444.97元。

结果表明，风险校准确定购电规模，日内更新提供合同修订依据，库存价值控制将有限电量配置给成本更高的后续缺口。四问在同一决策结构下逐层扩展，实现计划、调单与实时储能运行的协同。

关键词：微网调度；线性规划；风险校准；库存价值；滚动优化'''
    start=md.index('## 摘 要')+len('## 摘 要')
    stop=md.index('## 一 问题重述')
    md=md[:start]+'\n\n'+abstract+'\n\n'+md[stop:]
    replace_paragraph('（1）第一问按模板起点采样',
        '（1）附件中的00:10、00:20、…、24:00依次对应00:00—00:10、00:10—00:20、…、23:50—24:00区间，区间内功率按常值处理。四问均保持原始记录顺序，状态定义在区间边界，功率乘1/6小时换算为电量。结果模板按标注的区间起点匹配输出；跨入次日的第一问区间使用周期计划，不改变当天优化的初末边界。')
    md=md.replace('35,126.85','35,126.95')
    # Update every Q1 table from a fresh chronological solve, never by editing totals only.
    rows=[]
    for ids in [[60,72,84],[96,108,120]]:
        row=[]
        for i in ids:row.extend([q.interval.iloc[i],float(q.plan_kwh.iloc[i])])
        rows.append(row)
    rows.append(['全天购电量',s['plan_kwh'],'全天购电费',s['cost'],'—','—'])
    purchase=md_table(['时间段','购电量','时间段','购电量','时间段','购电量'],rows)
    bs=blocks(q);rows=[]
    for i in [0,2,4]:rows.append(bs[i]+bs[i+1])
    rows.append(['00:00 储电量',6000.,'—','24:00 储电量',6000.,'—'])
    storage=md_table(['时间段','充电量','放电量','时间段','充电量','放电量'],rows)
    for number,table in [(3,purchase),(4,storage),(12,purchase),(13,storage)]:
        md=re.sub(r'(^表 '+str(number)+r' [^\n]+\n\n)(?:\|[^\n]*\n?)+',
            lambda m:m.group(1)+table+'\n',md,flags=re.M)
    replace_paragraph('无储能时直接按净负载缺口购电',
        f"无储能时直接按净负载缺口购电，费用为{s['no_storage_cost']:,.2f}元。图4比较无储能、实际效率和无损储能三种条件下的最优费用。实际储能净节省{s['savings_yuan']:,.2f}元，降幅为{s['savings_percent']:.2f}%；将充放电损耗设为零后，费用进一步降至{eff.cost.iloc[-1]:,.2f}元。往返效率从64%提高到100%时，最优费用由{eff.cost.iloc[0]:,.2f}元降至{eff.cost.iloc[-1]:,.2f}元。")
    replace_paragraph('（a）费用桥接采用相同供需',
        '（a）三种条件采用相同供需与日初日末状态，费用条形从零起算，标注为元。（b）五组效率均重新求解，主设定为两侧各90%、往返81%；曲线表示效率变化后的系统最优费用。')
    replace_paragraph('图 3 的上面板给出供需',
        '图3上面板以正负方向区分充电与放电，并叠加外网购电；中面板给出边界储电量，下方面板给出分时电价。各面板共用时间轴，保留十分钟决策及145个状态边界。')
    replace_paragraph('图 5将普通计划费',
        '图5分别展示候选余量的总费用与紧急购电费。增加余量通常降低紧急补购支出，但会增加普通计划支出；岭回归70%余量的验证总费最低，为50.98万元。两种预测器使用相同验证日期和初始库存。')
    replace_paragraph('各列共用纵轴尺度',
        '图6按日期分列、按负载与光伏分行，同一行共用纵轴尺度。实线为实际观测，虚线为岭回归预测，均保留十分钟分辨率。')
    replace_paragraph('图10以点阵标出',
        '图10左侧按启用的预报组合列出全年节省，固定50%风险余量与基础执行器，分析信息更新的经济价值；右侧给出基础滚动、负载修正及库存价值控制的费用。两部分分别对应预报选择与执行策略的递进。')
    replace_paragraph('因此，价格变化同时影响',
        '因此，价格变化同时影响计划购电时段、日内调单与当前库存保留。图13按题目指定的四个日期分列，对齐价格、储电量及累计紧急购电的日内轨迹，展示两套策略在不同供需条件下的响应。')
    replace_paragraph('（a）实际价格与午夜预测',
        '图13第一行展示实际价格与午夜预测，第二行展示日前与滚动策略的储电量，第三行展示当日累计紧急购电量。每行共用纵轴尺度，竖虚线为6、12、18点。6月21日两策略均未发生实质紧急购电；9月23日滚动策略补购较多，说明单日效果不必与全年费用排序一致。')
    replace_paragraph('（a）两类策略各自相对即时平衡执行',
        '图14上、下两行分别为日前与滚动策略；左列为月度节省，右列为全期节省及95%配对区块重采样区间，均以千元为单位，各行采用独立且明确标注的线性刻度。采用2,000次、14日区块，日前区间为[59,151.20，186,368.40]元，滚动为[1,953.22，10,500.59]元。区间反映同年固定轨迹的条件波动，不校正模型开发与选择偏差。')
    mapping={'raw_q1_inputs':'raw_q1_inputs','result_q1_dispatch':'result_q1_dispatch',
        'fig05_forecasts':'q2_forecasts','raw_q3_forecasts':'q3_forecasts'}
    def new_image(m):
        name=Path(m.group(2)).stem
        return f'![{m.group(1)}](../figures/v8/{mapping.get(name,name)}.png)'
    md=re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',new_image,md)
    # Place figures within the same argument after explanatory text, so a large
    # inline picture cannot leave a half-empty preceding page.
    def move_figure(name,anchor,description=True):
        nonlocal md
        pattern=r'!\[[^\]]*\]\(\.\./figures/v8/'+name+r'\.png\)\n\n图 [^\n]+\n\n'
        if description:pattern+=r'[^\n]+\n\n'
        match=re.search(pattern,md);assert match,name
        block=match.group(0);md=md[:match.start()]+md[match.end():]
        index=md.index(anchor);md=md[:index]+block+md[index:]
    move_figure('raw_q1_inputs','为进行全年多次求解')
    move_figure('q2_forecasts','表 6 第二问全期预测误差')
    move_figure('q2_cost','表 7 第二问全期费用及期末储电量',False)
    move_figure('annual_price','价格误差用过去28个完整日')
    begin=md.index('### 10.1 模型的优点')
    end=md.index('## 十一 参考文献')
    md=md[:begin]+'''### 10.1 模型的优点

（1）四问共享能量平衡与储能递推，将供需误差、预报更新及波动电价依次接入，模型扩展关系清晰，便于分析信息与合同权限的作用。

（2）计划层以风险余量控制欠购，执行层依据后续缺口成本配置库存；保留、取消、新增与紧急补购分别结算，能够解释节费来源。

（3）自由弃电条件下的等价线性化降低求解规模，分段线性库存价值保留连续状态，适合十分钟决策与全年滚动计算。

### 10.2 模型的不足

（1）供需与电价依赖有限历史估计，残差范围不构成价格覆盖率保证；同年度开发与评价可能高估泛化效果，需要跨年度数据检验。

（2）库存价值采用历史路径均值，滚动分支以1.5倍价格近似后续调单机会，未联合优化所有未来合同与库存决策，因而不保证全局最优。

（3）模型未计入电池老化、区间内快速功率变化及网络约束。效率和合同清算口径采用工作假设，实际应用需按设备参数与交易规则校准。

### 10.3 模型的推广

（1）面向园区、商业建筑或充电站，可替换负载、光伏及储能参数，在相同状态递推中加入可控充电负荷与需求响应。

（2）可构造负载、光伏和价格的联合误差场景，以场景平均费用或风险度量扩展计划层，再用多年度数据检验风险与经济性的权衡。

（3）可在目标中加入电池吞吐量、循环寿命、碳成本及峰值需量费用，在经济性之外评价设备寿命与减排效果。

'''+md[end:]
    assert not re.search(r'GRU|神经网络|35,126.85|模板起点采样|周期曲线以24',md,re.I)
    (ROOT/'reports/完整论文_V8.md').write_text(md,encoding='utf-8')
    eqs=re.findall(r'\$\$\s*\n(.*?)\n\$\$',md,re.S)
    (ROOT/'reports/完整论文_V8公式.tex').write_text('\n\n'.join('\\[\n'+e+'\n\\]' for e in eqs),encoding='utf-8')
    manifest=dict(figures=len(re.findall(r'!\[',md)),tables=len(re.findall(r'^表[^\n]+\n\n(?=\|)',md,re.M)),
        display_equations=len(eqs),manuscript='reports/完整论文_V8.md',q1='artifacts/v8/q1_intervals.csv',
        other_results='artifacts/v5b',abstract_style='V6 method-result emphasis, V7 unified model')
    (ROOT/'artifacts/v8/paper_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':main()
