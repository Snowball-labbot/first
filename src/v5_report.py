"""V5 manuscript: preserve baseline evidence, add causal model improvement."""
from pathlib import Path
import json,re
import pandas as pd
from src.q12 import dump_json
from src.v5_delivery import SOURCES
import src.v2_delivery as delivery

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/v5'
def tab(label,title,heads,rows):
    def fmt(x):return f'{x:,.2f}' if isinstance(x,float) else str(x)
    return f'表 {label} {title}\n\n| '+' | '.join(heads)+' |\n| '+' | '.join(['---']*len(heads))+' |\n'+''.join('| '+' | '.join(map(fmt,r))+' |\n' for r in rows)+'\n'

def main():
    base=(ROOT/'reports/完整论文_V4.md').read_text(encoding='utf-8')
    gains={r['mode']:r for r in json.loads((OUT/'improvement.json').read_text(encoding='utf-8'))};g3,g4=gains[3],gains[4]
    new={r['strategy']:r for r in json.loads((OUT/'online_summary.json').read_text(encoding='utf-8'))}
    audit=json.loads((OUT/'verification.json').read_text(encoding='utf-8'));errors=pd.read_csv(OUT/'load_errors.csv')
    body=base[base.index('## 一 问题重述'):base.index('## 附录 A')]
    # Old graphics and price comparisons remain evidence for the fixed baseline.
    body=body.replace('主策略','基础策略').replace('主模型','基础模型')
    body=body.replace('三个随机种子17、42、2026分别训练','以17、42、2026为三个基种子，实际随机种子为基种子加拟合日编号，分别训练')
    body=body.replace('共39次拟合，CPU实测训练约126.56秒。','共39次拟合，原实验CPU训练约126.56秒。39份权重重新加载后的预测与缓存逐值一致；同期预测由原始价格重建，岭回归13次重新拟合亦与缓存一致。')
    def paragraph(prefix,replacement):
        nonlocal body
        pieces=body.split('\n\n');ix=[i for i,p in enumerate(pieces) if p.startswith(prefix)];assert len(ix)==1,(prefix,ix)
        pieces[ix[0]]=replacement;body='\n\n'.join(pieces)
    paragraph('本问允许利用新预报', '本问允许利用新预报修订计划，需比较调整费用与高价补购减少额。将新增、取消购电分解为非负变量，每次以当前储电量重解剩余时域，固定已执行区间。在此基础上，用已观测的负载误差修正后续预测，并按月利用已完成日期的费用选择预测方案，使滚动优化同时适应光伏信息更新与负载季节变化。')
    paragraph('本问将不确定性扩展', '本问将不确定性扩展至目标函数的电价系数。建立同期、岭回归和残差GRU三个预测器，在共同信息条件下比较价格误差与实际费用；固定供需预测及储能条件，以真实电价求名义最优下界。再将第三问的月度负载模型选择接入波动电价滚动调度，单独核验供需预测改进的增益。')
    body=body.replace('## 四 符号说明','''### 3.3 单位、富余电量与计划计费核验

附件1—4的五张工作表均无公式、隐藏行列或隐藏工作表。以另一读取程序逐值核对附件2的105,120个负载与光伏观测，换算后与建模输入一致；附件3的1,095处空日期是四行一组的结构记录，只补齐日期标识，不插补预测值。实际光伏零值和0.0076元/kWh的低电价均保留。

全篇采用电量平衡：功率乘1/6小时得到kWh，5,000 kW对应单时段充放电上限833.33 kWh。平衡式中的非负弃电变量允许供给富余；将其移项后即为“购电＋光伏＋放电＋紧急购电≥负载＋充电”，因此等式与供给不小于需求的约束等价。取消弃电变量而强行取等号才会错误地要求全部消纳。

普通费用按合同量核算。针对性测试取电池已满、计划购电1,000 kWh、负载100 kWh、无光伏、电价2元/kWh，实际弃电900 kWh，普通购电费仍为2,000元。第三、四问则按最终合同的保留、取消和新增量结算，未把实际消纳量代替计划量。

## 四 符号说明''')
    body=body.replace('### 8.4 更新时间的收益与费用构成','### 8.4 基础滚动策略的更新时间收益')
    insert=r'''### 8.5 面向提前时长的负载修正与月度模型选择

仅在零点预测负载，会忽略日内已观测偏差的持续性。设零点预测误差为实际负载减零点预测，以每次发布前18个十分钟区间的平均误差作为当前偏差x；历史目标小时的六个区间平均误差作为响应y。分别对6、12、18点及各未来目标小时拟合非负收缩回归：

$$
\hat\beta_{d,v,h}=\operatorname{clip}_{[0,1.5]}\left(\frac{\sum_{i\in H_d}x_{i,v}y_{i,v,h}}{1.2\sum_{i\in H_d}x_{i,v}^{2}}\right),\qquad H_d=\{\max(7,d-28),\ldots,d-1\}.
$$

其中日期从0编号；自第14日起启用，至少使用7个完整历史日；分母为零时系数取零。1.2倍分母对应20%的平方误差尺度惩罚，系数上限1.5限制短样本放大。修正后的预测为：

$$
\hat L^{A}_{d,v,t}=\max\{0,\hat L^{0}_{d,t}+\hat\beta_{d,v,h(t)}x_{d,v}\}.
$$

同一目标小时共享修正量，零点预测不变。50%风险余量仍从该预测方案此前28天的历史误差计算，避免沿用旧误差分布而重复补偿。表 ADAPT 比较全期各发布时刻的负载预测误差，单位均为kWh/十分钟。

'''
    rows=[]
    for hour in [6,12,18]:
        e=errors[errors.issue_hour==hour].set_index('candidate');b=float(e.loc['baseline','mae_kwh']);c=float(e.loc['adaptive','mae_kwh'])
        rows.append([f'{hour:02d}:00',b,c,f'{(1-c/b)*100:.2f}%'])
    insert+=tab('ADAPT','负载自适应修正的同目标误差对照',['发布时刻','基础MAE','修正MAE','降幅'],rows)
    insert+='''固定启用修正在1月22—31日使第三、四问滚动验证费分别增加972.85元和1,149.73元，因此不能依据后续全年收益回选一月方案。本文在验证结束后固定一项月度更新规则：2月使用一月选定的基础预测；3月起，每月首日分别回放此前28天的基础与修正方案，两者从该窗口起点的实际储电量出发，按历史真实费用选择下月方案，平局保留基础方案。候选模型、窗口、收缩系数与费用口径在全年评价前固定，月底真实数据仅在次月选择时可见。

两类电价情景均在3、6、7、8、9、10月启用修正，在其余月份使用基础预测。实际储电量连续跨月传递，历史回放的末状态不覆盖实时状态。全年固定启用修正的费用另作消融结果保存，其收益不作为回选规则。该比较属于同一年度数据上的顺序开发验证，并非未接触过的外部测试集。

'''
    insert+='事后对月度验证末端库存作敏感性检查：将每kWh储电的价值从0变化至样本最高紧急电价折算值，20次模型选择均保持不变，费用排序不依赖低估候选方案的剩余储电量。\n\n'
    body=body.replace('## 九 第四问',insert+'## 九 第四问')
    body=body.replace('### 9.4 预测优势如何转化为费用收益','### 9.4 基础调度下的价格预测收益')
    paragraph('价格误差降低与电费', '价格误差降低与电费下降并不等比例。容量、功率及峰谷价序限制了可调整动作，部分预测改进不会改变计划。上述费用对照固定V4的负载预测与调度规则，仅分离价格预测器贡献；GRU相对同期预测的7、14、28天配对区块重采样区间均跨零，故不据此宣称跨样本费用优势。V5的滚动交付结果另外加入第8.5节的月度负载模型选择，其费用见表 GAIN。')
    section='''### 9.6 月度模型选择的费用增益

固定电价和波动电价分别保持原50%余量、三次更新时间、储能约束及计费规则；波动电价继续采用一月选定的同期预测，只改变负载预测的月度选择机制。表 GAIN 给出与V4的配对顺序回测。

'''
    section+=tab('GAIN','V5与V4滚动策略的同口径结果',['指标','第三问','第四问滚动'],[
        ['V4总费/元',g3['baseline_cost'],g4['baseline_cost']],['V5总费/元',g3['v5_cost'],g4['v5_cost']],
        ['节省/元',g3['saving'],g4['saving']],['降幅',f"{g3['saving_percent']:.3f}%",f"{g4['saving_percent']:.3f}%"],
        ['V4紧急量/kWh',g3['baseline_emergency'],g4['baseline_emergency']],['V5紧急量/kWh',g3['v5_emergency'],g4['v5_emergency']],['初末SOC差/kWh','0／0','0／0']])
    section+=f'''第三问紧急购电减少{g3['baseline_emergency']-g3['v5_emergency']:,.2f} kWh，第四问滚动减少{g4['baseline_emergency']-g4['v5_emergency']:,.2f} kWh。两组对照的初末储电量分别相同，收益来自供需偏差处理与计划调整，未借助额外耗用期末库存。第三问相对仅午夜预报的15,045,126.93元下降{(1-g3['v5_cost']/15045126.92953643)*100:.2f}%；第四问相对保留的日前策略14,880,535.05元下降{(1-g4['v5_cost']/14880535.05)*100:.2f}%。

本年度节费与统计推广应分别评价。2,000次14天配对区块重采样中，第三问累计节费95%区间为[{g3['bootstrap'][1]['low']:,.2f}, {g3['bootstrap'][1]['high']:,.2f}]元，第四问为[{g4['bootstrap'][1]['low']:,.2f}, {g4['bootstrap'][1]['high']:,.2f}]元；7、28天区块结论一致，均跨零。因此V5取得了已核验的年度费用下降，尚不能据单年数据确认跨年稳定增益。

'''
    body=body.replace('## 十 模型检验与评价',section+'## 十 模型检验与评价')
    paragraph('从原始附件到实际轨迹', f'''对V5重新计算的六条334天轨迹，逐时重建最终计划和保留、取消、新增、紧急费用；另复核保留的第一、二问实际轨迹，第二问独立重算费用为14,132,612.16元。修改未来负载不改变此前发布的预测；20组月度验证窗口均截止于决策前一日，初始状态与真实历史一致。第一、二问的单位、富余供给及计划计费通过针对性测试，累计23项测试全部通过。

为避免同一列式与同一求解器检查相互印证，另消去储电状态，改用累计充放电约束重建LP；调单费用使用两条仿射函数的上图形式，独立于原增减量列式。36个随机及富余光伏案例、第一问和72个指定日滚动实例共109例中，最优值最大差异为{audit['max_solver_difference']:.2e}元；其中18例再与MILP对比一致。同步核对原始残差、对偶可行性、互补条件和原始—对偶差距，最大对偶差距为{audit['max_duality_gap']:.2e}元。该证书证明相应名义LP的最优性，不将预测误差下的全年实际费用称为全局最优。

'''+tab('AUDIT','主要数据与算法核验',['核验对象','检查内容','结果'],[
        ['原始附件','五张表、单位、日期与结构空值','数值不删改'],['输入复读','附件2两类实测105,120值','一致'],
        ['独立LP','109例另行列式与对偶证书','通过'],['整数对照','18例LP与MILP最优值','一致'],
        ['V5轨迹','6×334×144＝288,576时段','物理与费用一致'],['时间可见性','未来扰动及20组月度窗口','通过']]).rstrip())
    paragraph('模型的适用范围由数据', '模型的适用范围由数据与运行假设决定。十分钟平均功率忽略区间内快速波动，即时平衡控制未计及未来储能价值；退化与爬坡未进入目标。月度模型选择缓解单一一月窗口的季节代表性不足，但候选集合与窗口仍为有限设计；日末目标6,000 kWh仍是工作假设，全年实际费用尚无全局最优性保证。后续可用跨年数据检验模型选择、以跨日价值函数优化末端储能，并补充气象及退化成本。')
    paragraph('表12汇总', '表12汇总V5最终交付结果。第一、二问及第四问日前策略保留已核验结果；第三问及第四问滚动交付采用月度选择。图1—16及表8、表10、表11保留基础模型的对照证据，新增改进以表 ADAPT、表 GAIN 展示。')
    # Replace only the conclusion table; earlier baseline tables retain their values.
    begin=body.index('表 12 四问模型与基础策略结果') if '表 12 四问模型与基础策略结果' in body else body.index('表 12 四问模型与主策略结果')
    end=body.index('\n\n',body.index('| ---',begin)); # first blank after the full table
    body=body[:begin]+tab('12','四问V5交付结果',['问题','模型及策略','总费用/元','评价区间'],[
        ['一','等价LP与周期储能',35126.84858928963,'单日'],['二','岭回归＋70%余量',14132612.15924625,'334天'],
        ['三','滚动LP＋月度负载选择',g3['v5_cost'],'334天'],['四 日前','岭回归电价',14880535.05,'334天'],
        ['四 滚动','同期电价＋月度负载选择',g4['v5_cost'],'334天']]).rstrip()+body[end:]
    paragraph('第一问的等价线性规划获得', f'''确定性问题的最优日费用为35,126.85元，风险校准使第二问费用降至14,132,612.16元。进一步引入过去数据驱动的月度负载选择，第三问和第四问滚动费用分别为{g3['v5_cost']:,.2f}元、{g4['v5_cost']:,.2f}元，较V4节省{g3['saving']:,.2f}元和{g4['saving']:,.2f}元，且初末储电量保持一致。独立列式与对偶证书确认名义调度最优值；逐时物理、费用和信息时序复核确认实际运行可行。固定名义条件下1.002%的价格改善上限仍成立，V5的新增收益则来自供需预测与模型选择。''')
    abstract=f'''# 基于风险校准与在线模型选择的微网购电调度

## 摘 要

针对微网计划购电、日内调整和实时供电的时序约束，本文以总购电费用最小为目标，构建确定性调度、风险校准、滚动优化及在线模型选择的四问递进模型。

针对问题一，建立**确定性多期线性规划模型**，以循环消除证明等价处理充放电互斥约束。最优日购电量为59,482.70 kWh、费用35,126.85元，较无储能降低26.90%，并经混合整数规划核对。

针对问题二，建立**岭回归预测与分位数风险校准模型**，以70%历史误差分位余量降低欠购风险，储电量连续跨日。2—12月334天费用为14,132,612.16元，较同一岭回归无余量方案下降10.01%。

针对问题三，建立**非对称结算下的滚动线性规划模型**，并加入**收缩回归负载修正与月度模型选择**。在6、12、18点更新后，仅用历史数据选择负载预测方案，费用降至{g3['v5_cost']:,.2f}元，较基础滚动方案节省{g3['saving']:,.2f}元，紧急购电减少{g3['baseline_emergency']-g3['v5_emergency']:,.2f} kWh。

针对问题四，建立**残差GRU集成电价预测模型**并与同期、岭回归比较，GRU价格MAE为0.04366元/kWh，较岭回归降低8.09%。日前交付费用为14,880,535.05元；同期电价结合月度负载选择的滚动费用为{g4['v5_cost']:,.2f}元，较基础滚动方案节省{g4['saving']:,.2f}元。**共同名义可行域下界**表明，仅改进电价预测的GRU名义费用空间为1.002%。

109例独立列式与对偶证书核对通过，六条全年轨迹满足物理约束与计划计费规则。新增策略的年度节费已核实，区块重采样区间跨零，跨年稳定收益仍需外部数据检验。

关键词：微网购电；线性规划；分位数校准；滚动优化；在线模型选择

'''
    delivery.OUT=OUT;delivery.SOURCES=SOURCES;appendix=delivery.specified_tables()
    appendix=re.sub(r'表 (\d+)',lambda m:'表 '+str(int(m[1])-3),appendix)
    caption=13
    for item in json.loads((OUT/'specified_tables_manifest.json').read_text(encoding='utf-8')):
        for _ in range(2 if item['question']=='1' else 3):
            appendix=appendix.replace(f'表 {caption} ',f'表 {caption} 问题{item["question"]}（{item["date"]}） ',1);caption+=1
    ending='''## 附录 B 支撑文件与完整程序

五份结果工作簿分别保存各问最终交付策略。V5输出位于artifacts/v5，包含六条全年轨迹、各次计划版本、月度选择账本、负载回归系数、费用对照、109例最优性证书和输入指纹；第一、二问及第四问日前结果保留原已核验文件。图形保留基础对照，后续图形修订与数值版本分开管理。

原始数据单独读取，程序不修改附件。基础模型与价格预测沿用src/q12.py、src/q34_data.py、src/q4_forecast.py及V3程序；新增src/v5_model.py实现负载修正，src/v5_experiments.py与src/v5_online.py分别执行消融与顺序更新，src/v5_audit.py独立核验，src/v5_summary.py统计增益，src/v5_delivery.py写入并读回结果模板。以下列出完整核心计算程序。
'''
    text=abstract+body.rstrip()+'\n\n'+appendix+'\n\n'+ending
    labels=re.findall(r'^表 ([A-Z]+|\d+) [^\n]+\n\n\|',text,re.M)
    assert len(labels)==65 and len(set(labels))==65,(len(labels),labels)
    mapping={label:str(i) for i,label in enumerate(labels,1)}
    text=re.sub(r'表\s*(ADAPT|GAIN|AUDIT|\d+)',lambda m:'表 '+mapping[m[1]],text)
    (ROOT/'reports/完整论文_V5.md').write_text(text,encoding='utf-8')
    equations=re.findall(r'\$\$(.*?)\$\$',text,re.S)
    (ROOT/'reports/完整论文_V5公式.tex').write_text('\n\n'.join(equations),encoding='utf-8')
    dump_json(OUT/'paper_manifest.json',dict(figures=16,tables=65,display_equations=len(equations),main_tables=15,characters=len(text)))
    print('V5 manuscript',len(text),'characters',len(equations),'equations')
if __name__=='__main__':main()
