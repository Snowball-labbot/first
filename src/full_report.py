"""Assemble the four-question manuscript from verified frozen results."""
from pathlib import Path
import json,re
import numpy as np
import pandas as pd
from src.deliver_q12 import md_table,blocks,emergency_runs,DATES
from src.q12 import dump_json


def main():
    out=Path('artifacts/q34');q3=json.loads((out/'q3_selection.json').read_text());q4sel=json.loads((out/'q4_selection.json').read_text())
    q3s=[json.loads((out/f'q3_m{i}_summary.json').read_text()) for i in range(8)];s=q3s[q3['mask']]
    q4=json.loads((out/'q4_summary.json').read_text());ps=json.loads((out/'price_forecast_summary.json').read_text())
    chosen={m:next(r for r in q4 if r['mode']==m and r['forecast']==q4sel['selected'][str(m)]) for m in [2,3]}
    old=Path('reports/Q1_Q2修订稿.md').read_text(encoding='utf-8')
    body=old[old.index('## 一 问题重述'):old.index('### 7.4')]
    body=body.replace('本文只处理前两问。','本文依次研究确定性调度、预测误差、日内更新与波动电价四个层次。')
    body=body.replace('独立重读原始工作簿确认','重新读取原始工作簿确认')
    body=body.replace('## 二 问题分析','第三问进一步利用每日四个发布时刻的光伏预报，决定是否以及何时调整未执行的购电计划，并计入增购和减购费用。第四问使用附件中的实际波动电价，比较不同价格预测器在日前与滚动两类策略下的实际费用。\n\n## 二 问题分析')
    body=body.replace('普通购电按计划量结算，富余计划量不退款。','第一、二问普通购电按计划量结算，富余计划量不退款；第三、四问主动减购另按第八节的调整账本结算。')
    body=body.replace('第一问的供需曲线','第一问的供需曲线')
    introduction=f'''# 预测误差与波动电价下的微网购电和储能调度

## 摘 要

光伏出力、负载需求和外部电价同时影响微网运行，仅提高预测精度不能保证降低购电费用。本文建立统一的能量平衡与储能状态模型，将预测、计划、日内调整和实际结算连接起来，分析四种信息条件下的购电决策。

针对第一问，将十分钟购电和充放电量作为连续变量，引入二元变量保证充放电互斥，建立混合整数线性规划。在两侧效率各为90%的口径下，单日费用为35,126.95元，相较无储能降低26.90%；整数解与线性松弛下界一致。针对第二问，采用因果岭回归和历史净负载误差分位数余量，一月验证选定70%余量；2—12月334天总费用为14,132,612.16元，比同期无余量低26.50%。

针对第三问，将小时光伏预报积分为十分钟电量，建立保留计划版本、冻结已执行区间的滚动优化模型。按主结算假设，一月验证选定12:00和18:00更新、零额外余量，全年费用为{s['total_cost_yuan']:,.2f}元，比仅午夜预报低{100*(1-s['total_cost_yuan']/q3s[0]['total_cost_yuan']):.2f}%。八种更新时间组合和另一退款口径的实验表明，增加更新次数不保证实际费用单调下降。

针对第四问，在一致历史信息条件下比较同期、岭回归与三个随机种子的残差GRU。GRU集成的全期价格MAE为{ps['evaluation']['gru_mean']['mae']:.5f}元/kWh，岭回归为{ps['evaluation']['ridge']['mae']:.5f}元/kWh；但价格误差改善未必转化为电费降低。分别按一月实际费用选择两类策略，日前与滚动方案全年费用为{chosen[2]['total_cost_yuan']:,.2f}元和{chosen[3]['total_cost_yuan']:,.2f}元。

全部方案检验供电平衡、储能边界、充放电互斥、跨日连续性与费用账本。结论依赖明确的效率、时间标签和退款解释；预测驱动策略为可执行的经验方案，不等同于全局随机最优控制。

关键词：微网调度；混合整数规划；滚动优化；门控循环网络；预测误差

'''
    pieces=[introduction,body]
    def p(x):pieces.append(x.strip()+'\n\n')
    def eq(x):p('$$\n'+x+'\n$$')
    # Temporary figure/table IDs are renumbered once, preserving all references.
    fi=8;ti=7
    def fig(name,title,note):
        nonlocal fi;fi+=1
        p(f'![{title}](../figures/full/{name}.png)\n\n图 {fi} {title}\n\n{note}');return fi
    def table(title,headers,rows):
        nonlocal ti;ti+=1;p(f'表 {ti} {title}\n\n'+md_table(headers,rows));return ti
    p('四个指定日期的购电、充放电、日初日末储电量及紧急事件，集中列于附录 A；完整逐日计划分别写入题目指定结果文件。')
    p('## 八 第三问的日内滚动调整')
    p('### 8.1 新预报的价值与时间对齐')
    p('第三问新增的是带有发布时间的光伏信息，而不是未来实际出力。每个更新点应比较新计划可能避免的紧急购电与调整支出，并保护已经执行的交易。负载仍沿用第二问的日前岭回归，日内不使用未来负载真值校正预测；这一设计也使更新时间对照主要反映光伏预报和当前储能状态的作用。滚动优化具有不断用最新可用信息更新未来决策的结构，其思想可参见文献[4]；本文没有照搬该文的潮流或分布式控制模型。')
    p('附件3含365天、每日4次、每次24个小时预报，共35,040个数值。1,095个空日期位于同日四行预报的后3行，只在该结构内补齐。预报发布点与提前量逐行核验，无缺失、负数和非有限数；17,525个零值保留。预报“1小时”指发布后一小时，不是当天01:00。附件4的52,560个电价亦完整、非负且严格为正，范围0.0076—1.7936元/kWh。两附件均不做删点、缩尾或平滑观测。')
    p('设发布时刻为τ，小时预报端点为 Hτ,h，h＝1，…，24。发布时间处缺少零小时端点，采用刚结束的十分钟实际光伏均值作为边界代理，年初无历史时取零；该代理只用于预报曲线首段。以相邻整点之间的线性函数插值，并对每个十分钟区间作梯形积分：')
    eq(r'\hat V_{\tau,t}=\int_{a_t}^{b_t}\tilde P_\tau(u)\,du=\frac{\tilde P_\tau(a_t)+\tilde P_\tau(b_t)}{2}\Delta t.')
    p('此过程是预报分辨率转换，不是修改实际数据。实际电量仍按附件2原值乘1/6小时。当前实现每次只优化至本日24:00，预报中次日部分暂不用于跨日承诺，避免题目未规定的提前购入次日电量。图9展示6月21日的实际与不同版本预报。')
    fig('raw_q3_forecasts','同一日期不同发布时刻的光伏预报','各版本只从其发布时刻向后显示。新增预报不保证每个目标时段更接近实际；不能把18:00版本提前用于午夜决策。')
    p('### 8.2 多次调整的费用账本')
    p('题面给出减购50%违约电价和增购1.5倍价格，但没有完整说明取消部分是否退回原款。主模型取取消原价退款并扣50%违约费，即净回收0.5倍原价；另将“原款不退且额外支付50%违约费”单独重新优化作敏感性。该分歧必须体现在假设和结果中，不能默认为唯一解释。')
    p('令 g⁰ 为午夜计划，gᵏ 为第k次更新后的计划。每次调整对最近版本定义非负增购 a⁺ 和减购 a⁻。已执行区间不允许进入调整集合，未来计划保持非负：')
    eq(r'g_t^{k}=g_t^{k-1}+a_{k,t}^{+}-a_{k,t}^{-},\quad a_{k,t}^{\pm}\ge0,\quad 0\le a_{k,t}^{-}\le g_t^{k-1}.')
    p('单次同一区间不应同时增减。因为价格为正，同时增加和减少同量会额外支付正费用，可从最优解中消去；程序仍检查实际解没有这种循环。完整账本为：')
    eq(r'C_3=\sum_t p_tg_t^0+\sum_k\sum_{t\in\mathcal T_k}p_t(1.5a_{k,t}^{+}-0.5a_{k,t}^{-})+5\sum_t p_te_t.')
    p('对于多轮操作，新增单位支付1.5倍，随后取消也只净返还0.5倍，绝不返还先前支付的全部1.5倍；因而先增加再取消的往返费用为一倍价格，不产生虚假套利。总费用拆成午夜原始计划、历次增购、历次减购净退款、实际紧急购电四部分。另一个无退款解释只把负0.5系数改为正0.5，并重新求解整个策略。')
    p('### 8.3 滚动优化与余量校准')
    p('每次重新优化以当前真实已知储电量为初值，沿用物理可行域和名义日末6000 kWh下限。00:00以全部计划费用为目标；其余时刻已付款为常数，仅最小化尚可改变部分的调整费用。余量按对应发布版本、同一目标钟点此前28天净负载误差计算，并池化相邻三槽；不足28天使用已有历史。零余量单独作为候选。')
    eq(r'\boxed{\left\{\begin{aligned}\min_{g,c,d,w,S,z,a^+,a^-}\quad&\sum_{t\in\mathcal T_k}\hat p_{k,t}(1.5a_{k,t}^{+}-0.5a_{k,t}^{-})\\\mathrm{s.t.}\quad&g_t=g_t^{k-1}+a_{k,t}^{+}-a_{k,t}^{-},\\&g_t+\hat V_{k,t}+d_t=\hat L_t+r_{k,t}+c_t+w_t,\\&(g,c,d,w,S,z)\in\Omega,\\&S_{\tau_k}=S_{\tau_k}^{\mathrm{actual}},\quad S_{145}\ge6000,\\&a_{k,t}^{+}\ge0,\quad0\le a_{k,t}^{-}\le g_t^{k-1}.\end{aligned}\right.}')
    p('Ω沿用第一问中状态递推、所有状态点储能边界、母线侧功率限制和二元互斥，去掉原初末相等等式。第三问 p̂ 就是附件1的已知固定价格。求解后只按实际逐十分钟执行到下一更新点，未来轨迹随后可重新计算。没有更新的组保持已承诺计划，实际电池仍按即时余缺充放电并在不足时紧急补购。该控制规则保证供电可行，但不保证随机控制意义下最优。')
    p('一月22—31日验证三种余量与八个更新子集共24组；四组状态同源扩展为全部候选共同初值6244.256891 kWh，评价从2月1日共同状态9902.811288 kWh开始。图10给出验证费用矩阵，选择只依据该矩阵，之后冻结更新时刻和余量。')
    fig('process_q3_validation','余量与更新时间的验证费用','每格是完整10天实际总费用，单位万元；0表示不另加误差余量，横轴“无”仍使用午夜预报。')
    p('### 8.4 全年效果及是否需要其他预报')
    p(f'验证选定余量为{q3["quantile"]:.0%}，更新时刻为12:00与18:00。全年费用为{s["total_cost_yuan"]:,.2f}元，相对仅午夜组降低{100*(1-s["total_cost_yuan"]/q3s[0]["total_cost_yuan"]):.2f}%；紧急购电量为{s["emergency_kwh"]:,.2f} kWh。图11和表8列出同一余量下八个子集的事后比较。')
    table('第三问不同更新时间的全年比较',['更新时刻','总费/万元','紧急费/万元','期末SOC/kWh'],[[label,r['total_cost_yuan']/1e4,r['emergency_cost_yuan']/1e4,r['final_soc']] for label,r in zip(['仅午夜','06','12','06+12','18','06+18','12+18','06+12+18'],q3s)])
    fig('result_q3_cost','更新时间与全年费用','较深颜色为验证选定的12+18方案。全部更新的事后表现可用于解释，但没有用它替换已冻结的主方案。')
    p('新增信息能够支持更合适的调整，却伴随预报误差、调整交易和名义终端目标的影响。部分更新时间组合比仅增加另一时刻更差，说明不能简单把“预报更多”写成“回测必然更优”。本题这组数据支持采用日内更新，而具体更新时刻应在历史验证阶段确定。图12展示9月23日原计划、最终有效计划和连续储能状态。')
    fig('result_q3_dispatch','指定日期的计划变化与储能状态','竖虚线为选定更新时刻；午夜计划以灰虚线显示，最终有效计划以蓝实线显示。图中保留十分钟决策，不平滑购电尖峰。')
    sens=json.loads((out/'q3_fee_sensitivity.json').read_text());alt=sens[q3['mask']]
    p(f'无退款且额外罚款口径下，保持同一更新时刻与余量并重新求解，全年费用为{alt["total_cost_yuan"]:,.2f}元，主口径为{s["total_cost_yuan"]:,.2f}元。两者的实际轨迹不同，不能把差额理解为单纯退费金额。允许退款的名义最优调整可能取消过多电量并在实际误差下增加紧急费用，因此这类经验策略的事后费用不满足确定性“退款越多越省”的单调性。')
    p('## 九 第四问的电价预测与两类调度')
    p('### 9.1 波动价格的信息与结算')
    p('附件4每个供电区间只有一个实际价格，没有提供同一交付区间在不同交易时点的报价面板。主模型将未来价格视为未知，历史值仅在区间结束后可用；预测价格进入优化，实际交付区间价格乘对应系数用于回测结算。这是当前数据能够支持的明确假设，而非声称全年价格已在午夜公开。图13给出实际价格的全年变化。')
    fig('raw_q4_price','全年实际电价的日内范围与日均值','阴影为每天实际最小至最大值，不是置信区间；没有删除价格峰谷。价格低至0.0076元/kWh仍保留，不以MAPE作主指标。')
    p('### 9.2 公平预测接口与时间切分')
    p('每个起点τ直接预测未来144个十分钟价格。输入为目标钟点前一天和前一周的两条历史曲线，以及目标时刻、星期的正余弦编码；在各起点这些信息全部已知。同期、岭回归与GRU的信息来源相同，表示方式不同。前一天的末项最大为τ前一个已经结束的区间，避免把多步预测的“最近滞后”错误取成未来真值。')
    eq(r'\hat p_{\tau,j}^{\mathrm{seasonal}}=\frac{p_{\tau+j-144}+p_{\tau+j-1008}}{2},\qquad j=0,\ldots,143.')
    p('岭回归把两条历史价格、日历、两者差和乘积及各历史曲线均值和标准差组合为12维特征，按未来目标逐行拟合。标准化参数仅由训练窗口估计，正则强度在1、10、100中依据一月验证MAE选择，选得1。序列窗口每6小时移动；窗口重叠不能视为完全独立样本。全部训练目标必须在拟合时刻前结束，不能仅检查窗口起点。')
    p('模型于1月15日、22日初始化，此后每月月初从最近60天历史重新拟合。GRU每次把最近3天完整目标窗口作为内部早停验证，其他可用窗口训练，跨越分界的目标窗口剔除。内部验证只服务该次训练；一月22—31日外层验证用于比较方案；2—12月结果用于顺序样本外评价，不能反过来选择结构、种子或主方案。')
    p('### 9.3 残差 GRU 的训练')
    p('为避免小样本网络从零重建已有日周期，先以同期曲线作为基准，再用单层GRU学习偏差。输入维度6，隐藏维度32，每个位置输出一个价格残差，整体一次得到144步，不使用未来标签进行递归输入。门控关系采用PyTorch的实现约定[5]：')
    eq(r'r_j=\sigma(W_{ir}x_j+b_{ir}+W_{hr}h_{j-1}+b_{hr}),\quad z_j=\sigma(W_{iz}x_j+b_{iz}+W_{hz}h_{j-1}+b_{hz}).')
    eq(r'n_j=\tanh(W_{in}x_j+b_{in}+r_j\odot(W_{hn}h_{j-1}+b_{hn})),\quad h_j=(1-z_j)\odot n_j+z_j\odot h_{j-1}.')
    eq(r'\hat p_{\tau,j}=\max\{0.001,\ \hat p_{\tau,j}^{\mathrm{seasonal}}+s_y(w^Th_j+b)\}.')
    p('历史价格先按训练集尺度标准化，sy为相应标准差。输出头初始为零，初始预测因此等于同期基线。训练采用平滑L1损失、Adam学习率0.003、批大小32、梯度范数上限1，每次最多50轮；内部验证MAE连续6轮无改善则停止并恢复最好权重。价格下限0.001只作用于预测输出，且低于本数据实际最小价格，不属于清洗实际值。')
    p('固定种子17、42、2026；每次重训使用种子与拟合日索引之和，三个模型分别保存，再以等权均值构成预先定义的GRU集成。所有种子均进入结果表，不挑最好的一次替代其他结果。图14展示6月1日重训的内部验证收敛，仅代表该次训练，不能冒充全年的验证曲线。')
    fig('process_q4_learning','GRU 三个种子的内部验证过程','曲线在实际早停轮数结束；各次模型均恢复内部验证最优权重。其他月份的完整训练记录保留在支撑材料中。')
    p('### 9.4 预测精度与实际电费的区别')
    p('图15按题目指定四个日期展示午夜价格预测，表9统计每次起点当天剩余目标的MAE和RMSE。同一目标可能被不同起点预测，因此评价共120,240个“起点—目标”对，不是120,240个独立价格观测；原始全年观测仍为52,560个。')
    labels={'seasonal':'同期','ridge':'岭回归','gru17':'GRU 17','gru42':'GRU 42','gru2026':'GRU 2026','gru_mean':'GRU集成'}
    table('第四问价格样本外误差',['预测器','MAE/元每kWh','RMSE/元每kWh'],[[labels[n],r['mae'],r['rmse']] for n,r in ps['evaluation'].items()])
    fig('result_q4_forecast','四个指定日期的午夜电价预测','实际价红实线、岭回归蓝虚线、GRU集成紫点线，四面板统一尺度。各预测只使用其午夜之前的信息。')
    p(f'GRU集成MAE较岭回归低{100*(1-ps["evaluation"]["gru_mean"]["mae"]/ps["evaluation"]["ridge"]["mae"]):.2f}%，但低平均误差不能保证对极少数廉价充电槽的排序更准，也不能保证减少供需预测造成的紧急补购。为公平识别价格预测作用，两类策略分别固定负载、光伏、风险余量、初始SOC、更新时刻和结算，仅改变价格预测器。')
    p('第四问重算第二问时不使用附件3的日内信息，保持70%余量及午夜固定计划；重算第三问时使用其验证选定的12/18点更新与零余量。图16、表10给出全部价格预测器的费用。两类策略的主预测器分别只按一月实际费用在同期、岭回归、GRU集成中选择，得到日前岭回归和滚动同期方案。')
    table('第四问两类策略的实际费用',['预测器','日前总费/万元','滚动总费/万元'],[[labels[n],next(r['total_cost_yuan']/1e4 for r in q4 if r['mode']==2 and r['forecast']==n),next(r['total_cost_yuan']/1e4 for r in q4 if r['mode']==3 and r['forecast']==n)] for n in labels])
    fig('result_q4_cost','价格预测器对两类策略总费用的影响','点图采用局部费用范围以显示小差异，横轴明确标注绝对费用；不是从非零基线截断的柱图。三个种子是重复实验，不将其范围称为统计置信区间。')
    p(f'冻结的日前方案总费{chosen[2]["total_cost_yuan"]:,.2f}元、紧急购电{chosen[2]["emergency_kwh"]:,.2f} kWh；冻结滚动方案总费{chosen[3]["total_cost_yuan"]:,.2f}元、紧急购电{chosen[3]["emergency_kwh"]:,.2f} kWh。主方案并非各自全年事后最小值，这是严格保留验证／评价边界的结果。GRU试验表明网络能够改善部分价格误差，却不足以单凭该指标替换主购电策略。')
    p('## 十 综合验证与模型评价')
    p('### 10.1 数值与信息边界')
    p('四问共用的能量平衡、储能状态、互斥及单位换算均检查到10⁻⁵ kWh容差。第三、四问进一步按保存的午夜计划逐版本重建调整量，验证旧计划与前一版本一致、执行后的区间不改变、决策初始SOC等于实际轨迹中的对应值。独立读回原表比较实际负载、光伏和价格，并重新计算每个区间、每日与全期账本，避免图表文字只是引用同一个错误汇总。')
    p('基础测试包含可手算套利、容量边界、取消退款、无退款时不额外付费取消、增购计价、历史余量前缀不变、价格输入不含当前及未来值、GRU输出维度和梯度有限性。训练日志还逐次检查最后目标区间已经在拟合时结束。二至四问实际SOC连续跨日，表中同时报告期末存量；不能通过每天重置电池获得虚假的免费电量。')
    p('### 10.2 适用范围与改进')
    p('第一问在给定输入与所列假设下可提供数值精度内的确定性最优性证据。其余三问采用预测、名义优化和即时贪心控制的组合，只有本组实验中的可执行性与相对效果证据，没有解决完整随机最优控制，也没有严格的全年零紧急购电保证。使用更复杂的网络或增加预报次数，均须通过费用和物理执行结果检验。')
    p('主要限制包括：时间标签按区间右端点的解释、90%效率的单程／往返歧义、小时预报首段边界代理、减购退款口径、波动价格结算时点，以及较短的一月外层验证。模型暂不计电池寿命、充放电切换成本、爬坡约束及配电网络潮流，因此购电尖峰在数学上可行不等于最适宜直接下发实际设备。')
    p('改进应优先针对可检验的瓶颈：以多季节前向验证替代单月选择、学习预报误差随提前量的变化、增加终端储能价值或场景控制、将磨损与平稳性纳入费用，并在新增信息到来时重新评估风险余量。若采用上述改动，应作为新实验重新运行，不能在已经观察全年结果后修改参数却仍称同一测试集独立。')
    p('## 十一 结论')
    p(f'统一储能与计费口径后，确定性日调度费用为35,126.95元；供需不确定时，岭回归与风险余量方案全年费用为14,132,612.16元。第三问中，验证选定的12/18点更新方案费用为{s["total_cost_yuan"]:,.2f}元，支持在给定退款口径下利用日内信息，但不能据此保证所有更新时间组合更好。第四问的价格预测和两类调度完整重算表明：GRU有预测精度收益，经济收益还受价格排序、供需误差和调整制度共同影响，应以事先约定的验证费用选择主策略。')
    p('## 参考文献')
    p('[1] 全国大学生数学建模竞赛组委会. 2026年高教社杯全国大学生数学建模竞赛C题 微网与外部电网电力调控策略. 用户提供题面与附件.')
    p('[2] SciPy Developers. scipy.optimize.milp[EB/OL]. https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html. 访问日期2026-09-10.')
    p('[3] scikit-learn Developers. Ridge[EB/OL]. https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html. 访问日期2026-09-10. 本文采用NumPy实现相同岭目标.')
    p('[4] Morstyn T, Hredzak B, Aguilera R P, Agelidis V G. Model Predictive Control for Distributed Microgrid Battery Energy Storage Systems. IEEE Transactions on Control Systems Technology, 2018, 26(3):1107–1114. DOI:10.1109/TCST.2017.2699159.')
    p('[5] PyTorch Contributors. GRU, PyTorch 2.14 documentation[EB/OL]. https://docs.pytorch.org/docs/2.14/generated/torch.nn.GRU.html. 访问日期2026-09-11.')
    p('## 附录 A 指定日期与结果文件')
    p('以下结果均为最终实际运行口径，电量为kWh，费用为元；计划购电与最终有效购电分别说明，紧急量另外列出。第一问表格已在正文给出。完整结果为result1、result2、result3、result4-2和result4-3五份Excel。')
    # Preserve exact Q2 specified-day outputs, renumbering this appendix locally.
    oldtail=old[old.index('### 7.4'):old.index('## 八 模型检验')]
    oldtail=re.sub(r'表\s*(\d+)',lambda m:'表 '+str(int(m[1])+3) if int(m[1])>=8 else m[0],oldtail)
    p(oldtail.replace('### 7.4 题目指定日期的结果','### A.1 第二问指定日期').replace('#### ','##### '));ti=19
    f=pd.read_csv(out/f'q3_m{q3["mask"]}_intervals.csv.gz')
    p('### A.2 第三问指定日期')
    for date in DATES:
        g=f[f.date==date];p(f'{date} 的购电和储能分别见表 {ti+1}、表 {ti+2}。')
        rows=[]
        for i in range(2):
            row=[]
            for h in [10+i*6,12+i*6,14+i*6]:row.extend([f'{h:02d}:00-{h:02d}:10',float(g.plan_kwh.iloc[h*6])])
            rows.append(row)
        rows.append(['全天购电量',float(g.plan_kwh.sum()),'全天购电费',float(g.total_cost_yuan.sum()),'',''])
        table(date+' 第三问最终有效购电',['时间段','购电量','时间段','购电量','时间段','购电量'],rows)
        b=blocks(g);rows=[b[2*i]+b[2*i+1] for i in range(3)];rows.append(['00:00 储电量',float(g.soc_start_kwh.iloc[0]),'','24:00 储电量',float(g.soc_end_kwh.iloc[-1]),''])
        table(date+' 第三问储能',['时间段','充电量','放电量','时间段','充电量','放电量'],rows)
    p(f'第三问紧急购电见表 {ti+1}。');rows=[]
    for date in DATES:
        for r in emergency_runs(f[f.date==date]) or [['无',0.]]:rows.append([date,*r])
    table('第三问指定日紧急购电',['日期','时间段','紧急购电量'],rows)
    p('### A.3 第四问指定日期')
    p(f'表 {ti+1} 汇总两个冻结主方案，完整逐时与调整版本保存在相应结果文件。');rows=[]
    for mode in [2,3]:
        ff=pd.read_csv(out/f'q4_{mode}_{q4sel["selected"][str(mode)]}_intervals.csv.gz')
        for date in DATES:
            g=ff[ff.date==date];rows.append(['日前' if mode==2 else '滚动',date,float(g.plan_kwh.sum()),float(g.total_cost_yuan.sum()),float(g.emergency_kwh.sum()),float(g.soc_end_kwh.iloc[-1])])
    table('第四问指定日期汇总',['策略','日期','有效计划/kWh','总费用/元','紧急量/kWh','日末SOC/kWh'],rows)
    p('## 附录 B 支撑材料与完整程序')
    p('原题附件另行取得，不打包进支撑材料。支撑文件包括五份结果Excel、模型源程序、预测权重与训练日志、关键结果表和正式图。Python需要NumPy、SciPy、pandas、openpyxl、PyTorch；Word和图表重建另需Matplotlib、python-docx、Pandoc及本机文档工具，Excel导出调用Artifact Tool。模型主程序运行参数为 --data-root 指向原题目录，顺序为q12、q34、q4_forecast、q4_run。下面附完整建模与结果生成源程序，图像源和进一步复现说明随支撑文件提供。')
    text=''.join(pieces)
    # Display numeric precision: keep price metrics at five decimals (currency-scale MAE).
    for name,r in ps['evaluation'].items():
        oldrow=md_table(['x','y','z'],[[labels[name],r['mae'],r['rmse']]]).splitlines()[-1]
        text=text.replace(oldrow,f'| {labels[name]} | {r["mae"]:.5f} | {r["rmse"]:.5f} |')
    Path('reports/完整论文.md').write_text(text.rstrip()+'\n',encoding='utf-8')
    equations=re.findall(r'\$\$\s*\n(.*?)\n\$\$',text,re.S)
    Path('reports/完整论文公式.tex').write_text('\n\n'.join('\\[\n'+e+'\n\\]' for e in equations)+'\n',encoding='utf-8')
    dump_json(out/'paper_manifest.json',{'figures':len(re.findall(r'!\[',text)),'tables':len(re.findall(r'^表 \d+ [^\n]+\n\n\|',text,re.M)),
        'equations':len(equations),'q3_selected':s['strategy'],'q4_selected':q4sel['selected']})
    print('Manuscript generated',len(text),'characters')


if __name__=='__main__':main()
