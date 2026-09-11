"""Generate the full revised manuscript from verified V1/V2 evidence."""
from pathlib import Path
import json,re
import pandas as pd
from src.v2_delivery import OUT,table,specified_tables,load_trace
from src.q12 import dump_json


def main():
    original=Path('reports/完整论文.md').read_text(encoding='utf8')
    compare={x['question']:x for x in json.loads((OUT/'paired_comparison.json').read_text())}
    sums={x['strategy']:x for x in json.loads((OUT/'summary.json').read_text())}
    selections=json.loads((OUT/'selection.json').read_text())
    c3=compare['q3'];c4=compare['q4-3'];s3=sums['q3_v2'];s4=sums['q4_3_seasonal']
    abstract=f'''# 预测误差与波动电价下的微网购电和储能调度（Version 2）

## 摘 要

光伏和负载预测误差会同时影响计划购电、储能状态与紧急购电，预测精度的提高未必带来电费下降。本文建立统一的能量与费用账本，并对确定性、日前不确定性、日内更新和波动电价四种条件逐层建模。

针对第一问，在允许无成本弃电的条件下，证明充放电循环可以在保持购电量与全部储电状态不变的情况下消除，因而线性规划可给出与互斥整数模型同等费用的物理解。单日费用35,126.95元，较无储能降低26.90%。针对第二问，保留因果岭回归与70%历史误差余量，334天费用14,132,612.16元；降低名义日末储能目标的候选在一月较优、全年反而较差，未替换原策略。

针对第三问，以发布版本匹配的历史净负载误差补充50%分位数候选，一月选择12:00及18:00更新、日末名义下限6000 kWh、不作额外日内负载校正。全年费用降至{c3['candidate_cost']:,.2f}元，相比原策略降低{c3['saving_percent']:.2f}%，紧急购电量为{s3['emergency_kwh']:,.2f} kWh。针对第四问，保留日前岭回归策略，采用相同改进的滚动模型与一月选择的同期价格预测，费用为{c4['candidate_cost']:,.2f}元，较原滚动策略降低{c4['saving_percent']:.2f}%。

两项滚动改进与各自原策略的期末储电量相同，费用改善并非来自净消耗电池库存。保留GRU三种种子与集成的预测对照，按发布时刻分解误差，同时公开未改善的候选与事后表现更好的消融。研究属于同一年度数据上的模型修订与顺序回测，不构成新的独立年度验证。

关键词：微网调度；线性规划；误差校准；滚动优化；储能

'''
    body=original[original.index('## 一 问题重述'):original.index('## 八 第三问')]
    body=body.replace('以 SciPy 1.17.1 的 milp 接口调用 HiGHS [2]','原方案以 SciPy 1.17.1 的 milp 接口调用 HiGHS [2]')
    body=body.replace('../figures/q12_revision/fig03_efficiency.png','../figures/v2/q1_efficiency_points.png')
    body=body.replace('所有柱形从零开始。前两项比较储能作用，后两项比较效率解释；','点图以绝对费用标注。各点分别比较无储能、主效率和往返效率解释；')
    body=body.replace('../figures/q12_revision/fig06_cost.png','../figures/v2/q2_cost_points.png')
    body=body.replace('条形右端标注两者合计','用点的位置分别表示两项及总费用')
    proof=r'''
### 5.4 互斥约束的等价线性化

互斥不能由一般LP自动保证，但本题的自由弃电变量允许给出更强的结构结论。令ρ＝ηcηd≤1。对松弛解任一时段，作如下变换：

$$
x_t=\min\{c_t,d_t/\rho\},\quad c'_t=c_t-x_t,\quad d'_t=d_t-\rho x_t,\quad w'_t=w_t+(1-\rho)x_t.
$$

充电量和放电量均不增加，且至少一个变为零。由于ηc x＝ρx/ηd，储能增量完全不变；由于d′−c′−w′＝d−c−w，母线平衡也保持不变。购电、紧急购电和所有计划增减量不变，因此本文各类费用均不变。逐槽处理后得到符合互斥约束的物理解：

$$
C_{\mathrm{LP}}^{*}\le C_{\mathrm{MILP}}^{*}\le C_{\mathrm{transformed\ LP}}=C_{\mathrm{LP}}^{*}.
$$

因此，在本模型条件下，二者最优费用相等。Q1的变量可从865个减少到721个，并去掉144个二元变量；日内调整模型同理。实现使用HiGHS线性规划，求解后显式消除循环并重新核验物理约束，绝不直接把同时充放电的松弛解作为运行方案。

证明依赖允许非负、无上界、无额外费用的未利用电量，以及仅由购电和调整量决定的目标函数。若加入严格弃电限制、禁止弃用已买电量、充放电最短持续时间、切换费用等约束，应重新证明或恢复整数模型。本结论不等于所有储能规划都可删除互斥变量。相同最优费用也不保证求解器返回同一计划；在不确定输入下，不同同价计划仍可能产生不同事后费用。

'''
    body=body.replace('## 六 第二问',proof+'## 六 第二问',1)
    body+='''
### 7.4 日末目标修订的失败证据

名义日末6000 kWh是策略设置，而非问题二的硬约束。新增候选比较余量0、0.5、0.7、0.8、0.9与名义日末1200、6000、9000 kWh，共15组，均只用一月22—31日费用选择。选择到0.7和1200 kWh。但该候选全年费用与库存状况如下。

'''
    body+=table('表 8 第二问新终端候选与保留方案',['方案','总费/元','期末SOC/kWh'],[
        ['原策略（保留）',compare['q2']['v1_cost'],compare['q2']['v1_final_soc']],
        ['一月选择的新候选',compare['q2']['candidate_cost'],compare['q2']['candidate_final_soc']]])
    body+=f'''候选全年增加费用{-compare['q2']['saving_yuan']:,.2f}元，并少保留{compare['q2']['v1_final_soc']-compare['q2']['candidate_final_soc']:,.2f} kWh库存，不能称为改善。按全期最大固定电价估计补齐差额所需购电的压力金额为{compare['q2']['terminal_inventory_stress_yuan']:,.2f}元；它只是存量核算压力分析，不是虚构发生在年末后的实际交易。V2交付继续采用原策略。本次保留与替换属于同一数据集上的修订选择，不能再把交付组合声称为未经观察的独立测试结果。

'''
    q3methods=original[original.index('## 八 第三问'):original.index('### 8.4 全年效果')]
    q3methods=q3methods[:q3methods.index('一月22—31日验证三种余量')]
    body+=q3methods+r'''一月22—31日新增比较余量0、0.5、0.7，负载校正强度0、0.5、1，以及12/18点或6/12/18点更新，共18组，名义日末下限均为6000 kWh。此前原方案只比较0、0.7、0.9三个余量，因此没有覆盖适中的0.5。新增参数的价值来自更贴近调整制度下的欠购与多购权衡，而非使用更复杂的预测器。

校正候选只取更新时刻之前最近18个已完成区间的负载预测残差均值，并随未来提前量按36个时段的尺度指数衰减。午夜校正为零，更新点当前区间和未来实际值均不可进入：

$$
\bar\epsilon_\tau=\frac1m\sum_{i=\max(0,\tau-18)}^{\tau-1}(L_i-\hat L_i),\quad
\hat L'_{\tau,t}=\max\{0,\hat L_t+\beta\bar\epsilon_\tau\exp[-(t-\tau+1/2)/36]\}.
$$

残差池对相同发布版本与相同校正规则建立，使用此前28个完整日期及目标前后三槽。过去时段绝不按后来发布的信息回填。选择仍以验证实际费用为准，结果为q＝0.5、β＝0、12/18点更新。额外负载校正在验证期未得到支持，故主模型保留β＝0。

### 8.4 成本改善及来源

'''
    v1=json.loads(Path('artifacts/q34/q3_m6_summary.json').read_text())
    body+=table('表 9 第三问费用账本与运行量',['指标','原策略','V2'],[[label,float(v1[key]),float(s3[key])] for label,key in [
        ('午夜计划费/元','original_cost_yuan'),('增购费/元','increase_cost_yuan'),('减购净费用/元','decrease_cost_yuan'),
        ('紧急费/元','emergency_cost_yuan'),('总费/元','total_cost_yuan'),('紧急购电/kWh','emergency_kwh'),('未利用电量/kWh','spill_kwh'),('期末SOC/kWh','final_soc')]])
    body+=f'''V2节省{c3['saving_yuan']:,.2f}元，降幅{c3['saving_percent']:.2f}%。午夜多购增加常规支出，同时减少昂贵日内增购和五倍紧急购电，形成净节省。但未利用电量有所增加，因此不应把成本改善写成所有运行指标同时改善。两种方案均从9902.811288 kWh开始，期末均为{c3['candidate_final_soc']:,.2f} kWh，比较没有被期末存量差异混淆。

图10进一步给出两项滚动策略的累计节省路径。

![滚动策略累计节省](../figures/v2/rolling_savings.png)

图 10 第三问与第四问滚动策略相对各自原策略的累计节省；曲线上升表示累计节省扩大，局部回落表示该时段改进方案反而更贵。全部日期连续纳入，不挑选有利月份。

原稿八种更新组合的全年结果仍保留，但属于原余量设置下的比较；不能当作新q＝0.5的八组合结果。原策略相对只午夜更新具有收益，这支持研究日内信息价值。新策略只在事前列明的两个更新集合内选择，不能宣称12/18点已在所有可能更新时间中全局最优。

### 8.5 消融与结算敏感性

'''
    body+=table('表 10 第三问受控对照',['方案','总费/元','紧急购电/kWh'],[[label,sums[n]['total_cost_yuan'],sums[n]['emergency_kwh']] for label,n in [
        ('LP、原q=0规则','q3_lp_control'),('主方案q=0.5、β=0','q3_v2'),('相同q与时刻、β=1消融','q3_bias_ablation'),('不退款另罚50%，重新求解','q3_no_refund')]])
    body+='''仅改为LP的全年费用与原MILP结果有数元差异，不是节省的主要来源；相同名义最优值不等于浮点运算、同价计划与跨日执行路径逐位相同。β＝1消融的全年费用更低，但这是事后观察，不能覆盖一月选择。它说明负载校正值得后续独立季节验证，不能据此将其提升为已验证主策略。不退款敏感性保持参数不变并重新优化，实际计划也随之变化，差额不能解释为单纯退款金额。

'''
    q4methods=original[original.index('## 九 第四问'):original.index('### 9.4 预测精度')]
    body+=q4methods+'''### 9.4 按发布时间核对预测误差

全年价误差按发布时间拆分，避免把Q4-2实际只用午夜预报的情形与四次发布混合评价。同一目标在不同起点重复出现，不能作为独立重复观测。以下是未更改的已保存价格预测，在原始实际价格上重新计算的误差；本轮未重新训练GRU，原39次训练与三种种子权重均保留。

'''
    metrics=pd.read_csv(OUT/'price_errors_by_issue.csv')
    body+=table('表 11 各发布起点价格预测误差',['预测器','发布时刻','MAE/元每kWh','RMSE/元每kWh','配对数'],[
        [r.model,f'{r.issue_hour:02d}:00',f'{r.mae:.5f}',f'{r.rmse:.5f}',r.n_pairs]
        for r in metrics[metrics.model.isin(['seasonal','ridge','gru_mean'])].itertuples()])
    body+='''### 9.5 两类策略与候选保留原则

日前策略的低终端候选同时改变了储能目标。新候选的价格预测器只根据一月费用在同期、岭回归与GRU集成中选择；全年对照未显示其优于原日前方案。因此正式结果4-2保留原70%余量、6000 kWh名义下限及岭回归价格预测，不用事后最小费用的预测器替换。滚动策略采用q＝0.5、β＝0、12/18点更新，同期价格预测仍是一月选择结果。

'''
    body+=table('表 12 第四问交付与试验结果',['方案','总费/元','期末SOC/kWh'],[
        ['日前原策略（交付保留）',compare['q4-2']['v1_cost'],compare['q4-2']['v1_final_soc']],
        ['日前一月选择的新候选（未采用）',compare['q4-2']['candidate_cost'],compare['q4-2']['candidate_final_soc']],
        ['滚动原策略',c4['v1_cost'],c4['v1_final_soc']],['滚动V2（交付采用）',c4['candidate_cost'],c4['candidate_final_soc']]])
    body+=table('表 13 同一新滚动模型中的价格预测对照',['预测器','总费/元','紧急费/元'],[
        [name,sums[f'q4_3_{name}']['total_cost_yuan'],sums[f'q4_3_{name}']['emergency_cost_yuan']] for name in ['seasonal','ridge','gru_mean']])
    body+=f'''滚动V2比原策略节省{c4['saving_yuan']:,.2f}元，降幅{c4['saving_percent']:.2f}%，期末SOC相同。GRU集成的全期误差与新滚动费用均有优势，但不能因已经看到全年结果就取代一月选出的同期主模型。网络预测、风险余量和调整制度共同决定经济效果，单一平均误差不足以选购电策略。

## 十 综合核验与稳健性

### 10.1 原始数据与费用复算

四个输入附件与题面指纹逐一比对；原始时间与单位规范化后，逐时实际负载、光伏和价格与保存轨迹对照，未发现数值篡改或主费用算错。原稿4组Q2与21组Q3/Q4轨迹重新通过核验。本轮另对12组334天新轨迹检查供需平衡、SOC递推与跨日连续、容量与功率上限、互斥和全部费用分项；对保存的午夜计划逐版本重建增减及最终计划。每次求解状态与耗时单独保存，失败结果不得进入汇总。

第一问LP与MILP在原始输入及含光伏富余的随机小实例中交叉比较，并对退费与不退费两种修订目标比较最优费用。前缀扰动测试改变当前及未来输入，确认此前负载校正和风险余量不变。实际执行允许区间内即时平衡的近似仍保留，不能把它说成区间开始时知道完整实际平均值。

### 10.2 配对日费用与时间依赖

将原策略与候选在同一天的费用差配对，按7、14、28天循环区块重采样，每种长度2000次，考察结论对时间相关性的敏感性。下面区间是本年度日差序列的经验不确定性描述，不是不同年份的可靠覆盖保证。方法仍依赖区块可交换近似；季节非平稳性与模型修订后的选择偏差不能被Bootstrap消除。

'''
    body+=table('表 14 区块重采样下的全年节省区间',['问题','区块/天','2.5%/元','97.5%/元'],[
        [key,int(block),float(ci[0]),float(ci[1])] for key in ['q3','q4-3'] for block,ci in compare[key]['block_bootstrap_95pct'].items()])
    months=pd.read_csv(OUT/'monthly_comparison.csv')
    body+=table('表 15 各月滚动改进节省',['月份','第三问/元','第四问滚动/元'],[
        [month,float(months[(months.month==month)&(months.question=='q3')].saving.iloc[0]),float(months[(months.month==month)&(months.question=='q4-3')].saving.iloc[0])]
        for month in sorted(months.month.unique())])
    body+='''第三问与第四问滚动的各长度区块区间均为正，支持本数据内费用改善的稳定性；仍需新的季节或独立年度数据检验。第二问与第四问日前候选的区间跨越零且库存更少，不支持宣布其优于原模型。

### 10.3 模型边界与复现限制

时间按右端点解释、两侧90%效率、逐版本净退款50%、波动价按交付区间结算，均为明确工作口径。若官方进一步明确其它解释，需要全量重算。只优化到本日24:00没有充分利用次日预报，未来可研究跨日价值函数，但不能提前把未知次日实际曲线加入决策。

本轮没有凭观察峰值就删数，没有新增虚构气象或运行数据，也没有声称全局随机最优或全年零紧急购电。线性化减少的是计算复杂度；风险校准改善的是本数据中的决策费用，两种贡献应分开。低终端目标与简单负载校正的失败或不一致结果表明，单一一月窗口对季节泛化仍有限。

## 十一 结论

四问共用能量、时标、效率与结算约定。第一问给出可证明等价的LP求解形式并维持原最优费用；第二问保留原日前策略，避免把短窗内的库存消耗误当作全年改善。第三问新增适中风险分位数，降低昂贵补购与日内增购；第四问在波动价格下复现该滚动收益。完整指定日表和五份结果工作簿补齐第四问原稿展示不足。所有采用与未采用的候选均保留，交付属于可复算的Version 2研究稿。

## 参考文献

[1] 全国大学生数学建模竞赛组委会. 2026年高教社杯全国大学生数学建模竞赛C题：微网与外部电网电力调控策略. 用户提供题面与附件.

[2] SciPy Developers. scipy.optimize.milp; scipy.optimize.linprog. https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html. 访问日期2026-09-11. 本文计算使用SciPy 1.17.1.

[3] scikit-learn Developers. Ridge. https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html. 访问日期2026-09-11. 本文以NumPy实现带截距岭目标.

[4] Morstyn T, Hredzak B, Aguilera R P, Agelidis V G. Model Predictive Control for Distributed Microgrid Battery Energy Storage Systems. IEEE Transactions on Control Systems Technology, 2018, 26(3):1107–1114. DOI:10.1109/TCST.2017.2699159.

[5] PyTorch Contributors. GRU. https://docs.pytorch.org/docs/2.14/generated/torch.nn.GRU.html. 原试验使用CPU PyTorch 2.14，V2保留原模型权重与预测.

'''
    # Renumber all retained/new figures and remove stale manual figure numbers in references.
    # Existing figure captions 13/14 belong to retained Q4 diagrams, mapped to 10/11.
    body=body.replace('图13','图11').replace('图14','图12').replace('图 13','图 11').replace('图 14','图 12')
    text=abstract+body+specified_tables()+'''\n## 附录 B 可运行支撑材料\n\n五份结果文件位于artifacts/v2；src/v2_model.py为线性规划及因果调度，src/v2_experiments.py生成全部候选，src/v2_verify.py复算物理与费用，src/v2_delivery.py生成结果工作簿，src/v2_report.py生成正文。原价格预测由src/q4_forecast.py及其权重和日志复现，原日前保留方案由src/q12.py、src/q4_run.py复现。完整可运行源程序随支撑材料提供，不用截图替代代码。复现顺序见docs/RUN_V2.md。\n'''
    path=Path('reports/完整论文_V2.md');path.write_text(text,encoding='utf8')
    dump_json(OUT/'paper_manifest.json',{'source':str(path),'tables':text.count('\n| ---'),
        'figures':len(re.findall(r'!\[',text)),'display_equations':text.count('$$')//2,
        'characters':len(text),'adoption':'Q1/Q2/Q4-2 retained; Q3/Q4-3 revised; failed candidates disclosed'})
    print('V2 manuscript generated',len(text),'characters')


if __name__=='__main__':main()
