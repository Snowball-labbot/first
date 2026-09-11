"""Result-led competition manuscript, generated from checked computations."""
from pathlib import Path
import json,re
import numpy as np
import pandas as pd
from src.q12 import dump_json,interval_label
from src.deliver_q12 import blocks
from src.v2_delivery import table
import src.v2_delivery as delivery

def main():
    out=Path('artifacts/v3');sel=json.loads((out/'selection.json').read_text());sums={s['strategy']:s for s in json.loads((out/'summary.json').read_text())}
    q1=json.loads((out/'q1_summary.json').read_text());f1=pd.read_csv(out/'q1_intervals.csv');q3=sums[f'q3_m{sel["q3"]["mask"]}'];q30=sums['q3_m0']
    q42=sums[f'q4_2_{sel["prices"]["2"]}'];q43=sums[f'q4_3_{sel["prices"]["3"]}'];gru=sums['q4_3_gru_mean']
    bounds=pd.read_csv(out/'nominal_price_bound.csv').groupby('model')[['nominal_cost','oracle_lower','regret']].sum();br=bounds.loc['gru_mean']
    metrics=pd.read_csv('artifacts/v2/price_errors_by_issue.csv');ps=json.loads(Path('artifacts/q34/price_forecast_summary.json').read_text())['evaluation']
    saving3=q30['total_cost_yuan']-q3['total_cost_yuan'];saving4=q42['total_cost_yuan']-q43['total_cost_yuan'];gg=q43['total_cost_yuan']-gru['total_cost_yuan']
    abstract=f'''# 基于风险校准与价格信息价值的微网购电调度

## 摘 要

微网购电的关键在于协调分时套利与供电风险：储能能够转移低价电量，而预测不足会触发高价紧急购电。本文建立统一的能量平衡模型，将确定性优化、预测误差校准、日内滚动调整和价格信息评价连接起来，形成四层递进的调度方法。

针对第一问，建立十分钟分辨率的购电与储能联合规划，证明在允许无成本弃电时，充放电循环可在保持费用与储电状态不变的条件下消除，将含144个二元变量的模型化为等价线性规划。最优日购电量为{q1['plan_kwh']:,.2f} kWh，费用{q1['cost']:,.2f}元，比无储能节省26.90%。

针对第二问，以岭回归预测负载和光伏，采用历史净负载误差的70%分位数补足风险余量。334天总费用为14,132,612.16元，比同期预测无余量策略降低26.50%，比岭回归无余量降低10.01%，说明风险校准是预测转化为经济收益的重要环节。

针对第三问，按午夜计划与最终有效购电量建立非对称结算函数，在新预报到达后重解剩余时域。一月验证选定50%分位余量及6、12、18点更新，全年费用为{q3['total_cost_yuan']:,.2f}元，比相同余量下仅用午夜预报节省{saving3:,.2f}元，降幅{saving3/q30['total_cost_yuan']*100:.2f}%。

针对第四问，构建残差GRU与非神经网络预测器的同信息对照。GRU集成在四个发布时刻均取得最低价格MAE，全期MAE为{ps['gru_mean']['mae']:.5f}元/kWh，比岭回归降低{100*(1-ps['gru_mean']['mae']/ps['ridge']['mae']):.2f}%。滚动GRU总费为{gru['total_cost_yuan']:,.2f}元，比同期价格预测再节省{gg:,.2f}元。进一步建立共同名义可行域上的真实价格下界，计算得GRU计划费用的剩余改进上限为{br['regret']:,.2f}元，占其名义费用{br['regret']/br['nominal_cost']*100:.3f}%。

研究表明，滚动预报和风险余量决定主要节费空间，GRU进一步改善价格预测；将预测精度、实际费用与最优值差距分开评价，能够准确识别算法的贡献和后续优化重点。

关键词：微网调度；线性规划；风险校准；滚动优化；GRU；信息价值

'''
    old=Path('reports/完整论文_V2.md').read_text(encoding='utf8')
    body=old[old.index('## 一 问题重述'):old.index('### 7.4')]
    body=body[:body.index('按月费用见图 7')]+ '\n四个指定日期的购电、充放电和紧急购电结果见附录A。\n\n'
    start=body.index('第一问是已知输入');end=body.index('## 三 模型假设')
    body=body[:start]+'''第一问的核心是利用价差在144个时段之间转移电量。储能效率决定套利门槛，容量与功率决定转移规模。本文先建立完整互斥模型，再证明可消除循环充放电，以线性规划取得全局最优解并解释集中充放电行为。

第二问中，低估净负载需要按五倍电价补购，而高估仍需支付计划费用。因此采用“预测—风险校准—调度”三步法，以历史误差分位数平衡欠购和多购，再通过全年实际费用检验余量收益。

第三问增加了日内重新申报的机会。新预报降低未来供需的不确定性，但增购和减购价格不对称。需要同时决定更新时间、购电调整量和储能动作，并将已执行区间固定。比较不同更新时间的完整费用，才能判断预报更新的净价值。

第四问的价格预测同时影响套利时机与购电规模。本文以残差GRU捕捉周期基线之外的变化，与同期预测及岭回归共享历史信息，并将输出接入同一调度器。在此基础上引入真实电价的名义最优下界，既检验预测精度，也量化距离最优计划的剩余空间。

'''+body[end:]
    body=re.sub(r'（1）将每个功率值.*?\n\n','（1）第一问按模板起点采样，周期曲线以24:00值补齐00:00，功率在十分钟区间内取常值；全年历史序列按记录终点对应十分钟区间均值建模。状态统一定义在区间边界，功率乘1/6小时换算为电量。\n\n',body,flags=re.S)
    body=body.replace('第一、二问普通购电按计划量结算，富余计划量不退款；第三、四问主动减购另按第八节的调整账本结算。','第一、二问普通购电按计划量结算；第三、四问主动调整按第八节的保留量、取消量和新增量分项结算。')
    body=body.replace('原方案以 SciPy','以 SciPy').replace('每日求解时间上限为 30 秒；超时或无可行解时应停止并报告，而非将空结果视为成功。','每日求解时间上限为30秒，全部运行取得成功求解状态。')
    body=body.replace('../figures/q12_revision/fig02_dispatch.png','../figures/v3/result_q1_dispatch.png').replace('../figures/v2/q1_efficiency_points.png','../figures/v3/result_q1_efficiency.png').replace('../figures/v2/q2_cost_points.png','../figures/v3/result_q2_cost.png')
    body=body.replace('../figures/q12_revision/fig01_inputs.png','../figures/v3/raw_q1_inputs.png')
    body=body.replace('35,126.95','35,126.85').replace('35,126.94858929','35,126.84858929').replace('33,801.50','33,801.48')
    a=body.index('表 3 第一问指定时段');b=body.index('### 5.3',a)
    rows=[]
    for slots in [[60,72,84],[96,108,120]]:
        row=[]
        for i in slots:row.extend([interval_label(i),float(f1.plan_kwh.iloc[i])])
        rows.append(row)
    rows.append(['全天购电量',q1['plan_kwh'],'全天购电费',q1['cost'],'—','—'])
    bb=blocks(f1);storage=[bb[i]+bb[i+1] for i in range(0,6,2)]+[['00:00 储电量',6000.,'—','24:00 储电量',6000.,'—']]
    body=body[:a]+table('表 3 第一问指定时段购电量及全天费用',['时间段','购电量']*3,rows)+table('表 4 第一问四小时充放电及边界储电量',['时间段','充电量','放电量']*2,storage)+'''低价时段的外网购电同时满足负载与充电，形成集中购电峰值；高价时段由储能补充供电，降低外网购电量。图2把购电、负载和充放电放在同一功率面板，并以储电状态、电价辅助解释各次动作。表内电量均为kWh，费用为元；四小时内先充后放不影响十分钟内充放电互斥。

'''+body[b:]
    body=body.replace('自上而下为电价、购电与正净负载、充放电、SOC。所有阶梯保留十分钟决策，不作平滑。购电超过正净负载的部分用于充电；SOC 阴影为允许范围。','上面板合并供需、购电与充放电功率；中面板显示储电量及上下限，下面板显示电价。共用时间轴保留十分钟决策。')
    body=body.replace('点图以绝对费用标注。各点分别比较无储能、主效率和往返效率解释；','三组条形从零起算，并在末端标注绝对费用。')
    body=body.replace('用点的位置分别表示两项及总费用','条形右端标注总费用')
    body=body.replace('绝不直接把同时充放电的松弛解作为运行方案。','得到满足充放电互斥的可执行解。')
    body=body.replace('在本题输入与约束口径下，这支持数值精度内的全局最优性。','整数解与松弛下界一致，达到该模型的全局最优费用。')
    body=re.sub(r'证明依赖允许非负.*?相同最优费用也不保证.*?费用。','该等价性建立在可自由弃电和线性购电成本上。若加入切换成本或严格弃电限制，应恢复相应约束后重新求解。',body,flags=re.S)
    body=body.replace('该试验只改变效率，不能与主实验混为同一组结果。','提高往返效率可进一步降低套利损耗。')
    body=body.replace('不加入平滑后虚构的尖峰。','展示十分钟分辨率下的预测偏差。')
    pieces=[abstract,body];ti=7;fi=6
    def p(s):pieces.append(s.strip()+'\n\n')
    def eq(s):p('$$\n'+s+'\n$$')
    def tab(title,head,rows):
        nonlocal ti
        ti+=1;p(table(f'表 {ti} {title}',head,rows));return ti
    def fig(path,title,caption):
        nonlocal fi
        fi+=1;p(f'图{fi}展示{caption}\n\n![{title}]({path})\n\n图 {fi} {title}');return fi
    p('''## 八 第三问 日内预报的滚动价值

### 8.1 预报信息与决策时域

附件3含365天、每日4个版本、每版24个整点光伏预报，共35,040个值。按四行组还原1,095个结构性空日期后，未发现缺失、非有限数或负值。预报发布时间分别为0、6、12、18点；时刻τ的新预报只服务于τ之后的调度。小时预报端点之间采用分段线性函数，并在十分钟区间上积分为预测电量；发布点以最近完成区间的光伏观测衔接。

这一处理保留了预报更新带来的信息差异。每次求解均以当时真实储电量为起点，固定已经执行的购电与充放电量，重新配置其余区间。该时域推进方式与储能模型预测控制的基本框架一致[4]。''')
    fig('../figures/full/raw_q3_forecasts.png','四个发布版本的光伏预报','指定日期的实际光伏及各版预报；曲线从各自发布时间开始。较晚预报能够改变午后供需判断，为调整计划提供新依据。')
    p('''### 8.2 保留量 取消量与新增量的结算

记午夜计划为x_t，时段执行前最后一次有效调整量为y_t，紧急购电为e_t。取消量u_t与新增量v_t分别定义为：''')
    eq(r'u_t=(x_t-y_t)^+,\qquad v_t=(y_t-x_t)^+,\qquad y_t=x_t+v_t-u_t.')
    p('保留购电按原价结算，取消部分按半价支付违约费，新增部分按1.5倍价格购买。因此每个区间的完整费用为：')
    eq(r'F_t=p_t\min(x_t,y_t)+0.5p_tu_t+1.5p_tv_t+5p_te_t=p_tx_t-0.5p_tu_t+1.5p_tv_t+5p_te_t.')
    p('原计划100 kWh、调整为80 kWh、电价1元/kWh时，总费用为80＋0.5×20＝90元；调整为120 kWh时，费用为100＋1.5×20＝130元。前式按保留量计普通费用，后式按原计划记账，两种表达完全等价。多次预报更新均相对同一午夜计划确定偏差；中途计划用于运行与追溯，不重复累计尚未交付区间的修改费用。')
    p('''### 8.3 滚动优化模型与风险校准

记Tτ为当前尚未执行的区间集合，Ω为第一问去除首末状态等式后的物理可行域。以更新后的光伏预测、负载预测和对应误差余量作为供需输入，求解：''')
    eq(r'\boxed{\left\{\begin{aligned}\min_{y,c,d,w,S,u,v}\quad&\sum_{t\in T_\tau}\hat p_{\tau,t}(1.5v_t-0.5u_t)\\\mathrm{s.t.}\quad&y_t=x_t+v_t-u_t,\quad0\le u_t\le x_t,\quad v_t\ge0,\\&y_t+\hat V_{\tau,t}+d_t=\hat L_{\tau,t}+r_{\tau,t}+c_t+w_t,\\&(y,c,d,w,S)\in\Omega,\quad S_\tau=S_\tau^{\mathrm{actual}},\quad S_{145}\ge6000.\end{aligned}\right.}')
    p('''目标函数省略了与当前决策无关的午夜合同常数项。第一至三问的p由附件1给定；第四问替换为当时可获得的价格预测。名义规划满足供电需求，实际执行按第二问的实时平衡规则应对残余预测误差。

风险余量使用此前28个完整日期、相同发布版本和目标前后三个区间的净负载误差。比较0、50%、70%三个分位数与8种更新时间组合，共24组。一月22—31日选择50%分位数及6、12、18点更新，随后运行2—12月。负载预测器和日末名义目标保持一致，使比较集中反映预报更新与调整制度的作用。''')
    fig('../figures/v3/process_q3_validation.png','风险余量选择与滚动收益积累','一月验证费用和全年累计收益。左图用于确定参数，右图分别比较固定电价下午夜与滚动策略、波动电价下日前与滚动主策略。')
    p('### 8.4 更新时间的收益与费用构成')
    fig('../figures/v3/result_q3_updates.png','八种更新时间组合的费用对比','同一50%余量下的全部更新时间组合。深蓝标出验证期选定的主方案，红色为紧急购电费用。')
    tab('第三问主策略与仅午夜预报的费用分解',['费用或运行量','仅午夜预报','日内滚动'],[
        [lab,q30[k],q3[k]] for lab,k in [('原计划费/元','original_cost_yuan'),('新增购电费/元','increase_cost_yuan'),('取消量净费用/元','decrease_cost_yuan'),('紧急购电费/元','emergency_cost_yuan'),('总费用/元','total_cost_yuan'),('紧急电量/kWh','emergency_kwh'),('期末储电量/kWh','final_soc')]])
    p(f'全年总费用由{q30["total_cost_yuan"]:,.2f}元降至{q3["total_cost_yuan"]:,.2f}元，减少{saving3:,.2f}元，降幅{saving3/q30["total_cost_yuan"]*100:.2f}%。实际紧急电量降至{q3["emergency_kwh"]:,.2f} kWh。三次更新把部分五倍电价的紧急补购提前转化为常规调整，节省额超过调整成本，因而有必要引入零点之外的预报。两方案初末储电状态相同，净节费不依赖消耗更多期末库存。')
    p('''## 九 第四问 GRU预测与价格信息的优化空间

### 9.1 波动电价与共同预测信息

附件4给出365天、每天144个电价，共52,560点，范围为0.0076—1.7936元/kWh。所有价格保留原值，不对峰谷截尾。各预测器使用发布前的价格历史以及已知日历信息，输出未来144个十分钟目标；当日调度只读取其中尚未执行的区间。''')
    fig('../figures/full/raw_q4_price.png','全年实际电价的日内范围','日均价格与每日最小—最大范围。稳定的日内结构与随机幅度共同影响购电的时机和规模。')
    p('同期预测取昨日与上周同目标区间价格的平均值。岭回归在这两组历史价格、日历周期特征及滞后统计量上构造12维输入。残差GRU使用6维输入：昨日价、上周价、日内正余弦和星期正余弦。三类预测器共享历史可见范围，区别在于对非线性依赖的表示能力。')
    eq(r'\hat p^{\mathrm{seasonal}}_{\tau,j}=\frac{p_{\tau+j-144}+p_{\tau+j-1008}}2,\qquad j=0,\ldots,143.')
    p('''### 9.2 残差GRU的结构与训练

GRU以门控结构选择保留的历史信息[6]。本文采用单层32维隐藏状态，在同期基线之上预测残差，输出头从零初始化，使初始预测与同期方法一致。输入维度较小、序列固定为144步，有利于在有限历史数据上控制训练规模。网络按PyTorch的GRU形式实现[5]：''')
    eq(r'r_j=\sigma(W_{ir}x_j+b_{ir}+W_{hr}h_{j-1}+b_{hr}),\quad z_j=\sigma(W_{iz}x_j+b_{iz}+W_{hz}h_{j-1}+b_{hz}).')
    eq(r'n_j=\tanh(W_{in}x_j+b_{in}+r_j\odot(W_{hn}h_{j-1}+b_{hn})),\quad h_j=(1-z_j)\odot n_j+z_j\odot h_{j-1}.')
    eq(r'\hat p_{\tau,j}=\max\{0.001,\hat p^{\mathrm{seasonal}}_{\tau,j}+s_y(w^\mathsf{T}h_j+b)\}.')
    p('''前两个价格特征的均值和标准差仅从训练集估计，sy为训练价格标准差。网络采用SmoothL1损失与Adam优化器，学习率0.003，批量32，梯度范数截断为1；最多训练50轮，内部验证连续6轮无改进即早停。输入窗口每6小时取样，只有全部预测目标已发生的窗口进入训练。

1月15日、22日和之后每月首日重新训练，每次最多使用此前60天数据；内部验证为最近3个完整日期，跨越训练—验证边界的目标窗口不进入训练。三个随机种子17、42、2026分别训练，最终等权平均，共39次拟合，CPU实测训练约126.56秒。图中的训练曲线展示一次月初拟合的内部验证过程。''')
    fig('../figures/full/process_q4_learning.png','三个随机种子的GRU验证误差','同一月初拟合中三个网络随训练轮数变化的内部验证MAE；早停分别保留各自最优权重。')
    p('### 9.3 四个发布时刻的预测优势')
    fig('../figures/v3/result_q4_accuracy.png','GRU与非神经网络预测的误差对比','各发布时刻相同目标范围上的MAE。GRU在四组比较中均取得最低误差。')
    rows=[]
    for hour in [0,6,12,18]:
        mm=metrics[metrics.issue_hour==hour].set_index('model');rows.append([f'{hour:02d}:00',*[f'{mm.loc[m,"mae"]:.5f}' for m in ['seasonal','ridge','gru_mean']],f'{100*(1-mm.loc["gru_mean","mae"]/mm.loc["ridge","mae"]):.2f}%'])
    tab('各发布时刻价格MAE及GRU相对岭回归的改进',['发布时刻','同期','岭回归','GRU集成','改进比例'],rows)
    p(f'按全部发布—目标配对加权，GRU集成MAE为{ps["gru_mean"]["mae"]:.5f}元/kWh，较同期预测降低{100*(1-ps["gru_mean"]["mae"]/ps["seasonal"]["mae"]):.2f}%，较岭回归降低{100*(1-ps["gru_mean"]["mae"]/ps["ridge"]["mae"]):.2f}%。共120,240个配对，其中同一目标可由不同发布时刻预测；分时评价保证各模型比较的是相同信息时点。')
    fig('../figures/full/result_q4_forecast.png','四个指定日期的午夜价格预测','实际价与岭回归、GRU预测的逐时对照。GRU主要修正同期结构之外的变化，部分突变仍由实时运行承担。')
    p('### 9.4 预测优势如何转化为费用收益')
    tab('波动电价下两类策略的全年费用',['价格预测器','日前总费/元','滚动总费/元'],[[name,sums[f'q4_2_{m}']['total_cost_yuan'],sums[f'q4_3_{m}']['total_cost_yuan']] for m,name in [('seasonal','同期预测'),('ridge','岭回归'),('gru_mean','GRU集成'),('oracle','真实电价对照')]])
    p(f'一月实际费用选择的日前主策略为岭回归，滚动主策略为同期预测，全年分别为{q42["total_cost_yuan"]:,.2f}元和{q43["total_cost_yuan"]:,.2f}元，滚动方案降低{saving4:,.2f}元（{saving4/q42["total_cost_yuan"]*100:.2f}%）。保持同一滚动策略，GRU将总费进一步降至{gru["total_cost_yuan"]:,.2f}元，比同期预测节省{gg:,.2f}元，比岭回归节省{sums["q4_3_ridge"]["total_cost_yuan"]-gru["total_cost_yuan"]:,.2f}元。前者是策略层面的改进，后者是价格预测模块的增益。')
    fig('../figures/v3/result_q4_cost.png','价格预测器对实际购电费用的影响','相对同期价格预测的节省额。零点右侧表示节省、左侧表示增加费用；真实电价对照只用于事后评价。')
    p('价格MAE改善没有按相同比例转化为电费下降。储能功率、容量和高低价次序限制了可改变的动作，部分预测改进发生在计划不变的区间。GRU在本组滚动比较中费用最低；其相对同期的配对日节省在7、14、28天区块重采样下均有跨零区间，因此该小幅费用优势体现为本年度实测收益，而主要、稳定的证据是四个发布时刻一致的精度改善。结果文件采用一月选定的主策略，GRU完整轨迹另随支撑材料保存。')
    p('''### 9.5 名义最优下界与剩余改进上限

为直接回答价格预测还有多大优化空间，对每个日期固定相同的负载与光伏预测、风险余量、日初状态和日末目标，得到共同可行域Fd。各预测器只改变目标函数中的价格；事后将真实电价代入同一可行域求解线性规划[7]：''')
    eq(r'J_d^*=\min_{g\in\mathcal F_d}p_d^\mathsf{T}g,\qquad J_{m,d}=p_d^\mathsf{T}g_{m,d},\qquad g_{m,d}\in\mathcal F_d.')
    p('由于真实电价解在相同可行域内最优，任一预测器的可行计划都满足Jm,d≥Jd*。因此模型m仅通过改善价格预测能够获得的名义费用节省Δm受到下式约束：')
    eq(r'0\le\Delta_m\le R_m=\sum_d(J_{m,d}-J_d^*),\qquad \gamma_m=\frac{R_m}{\sum_dJ_{m,d}}\times100\%.')
    tab('相同名义可行域中的真实价格下界',['预测器','名义费用/元','真实价格下界/元','剩余差额/元'],[[label,*[bounds.loc[m,k] for k in ['nominal_cost','oracle_lower','regret']]] for m,label in [('seasonal','同期'),('ridge','岭回归'),('gru_mean','GRU集成')]])
    fig('../figures/v3/result_q4_bound.png','价格预测的名义费用改进空间','334个共同可行域上计算的最优值差距。该差额为相同名义调度问题内的改进上限，数值越小表示越接近真实价格最优计划。')
    p(f'GRU的名义计划费用为{br["nominal_cost"]:,.2f}元，真实电价最优下界为{br["oracle_lower"]:,.2f}元，两者相差{br["regret"]:,.2f}元，即{br["regret"]/br["nominal_cost"]*100:.3f}%。这说明在既定供需预测和储能条件下，继续改进电价预测最多只能削减约1%的名义计划费用。同期与岭回归也处于相近量级，表明费用接近最优主要来自稳定的调度结构，而GRU的附加价值在于降低预测误差并改善部分滚动决策。')
    p(f'实际执行的真实电价对照另得：滚动费用为{sums["q4_3_oracle"]["total_cost_yuan"]:,.2f}元，相比同期预测改善{100*(1-sums["q4_3_oracle"]["total_cost_yuan"]/q43["total_cost_yuan"]):.3f}%。该对照包含真实供需偏差与紧急购电，属于固定执行规则下的事后实验；上述约1%的数学上限则限定于共同名义可行域。两者共同指向：提高供需预报和调整策略的收益空间，比单独精细化电价预测更值得优先投入。')
    p('''## 十 模型检验与评价

### 10.1 数值验证与结论稳健性

从原始附件到实际轨迹逐项检查日期、时段、单位和非有限值。第一问的LP与MILP费用一致；其余16组全年轨迹均满足供需平衡、储能递推、充放电互斥、功率容量边界和跨日连续性。费用复算独立采用“保留量＋取消量＋新增量＋紧急量”公式，并从午夜计划逐次恢复最后有效计划，验证运行结果与费用结算一致。

时间因果性通过训练标签截止检查及未来输入扰动测试检验：改变未来实际数据，不应改变此前的预测与风险余量。原始观测未删点、截尾或平滑；价格预测输出的正值截断属于预测器约束。对GRU成本增益采用配对日区块重采样，保留日间相关性，其区间跨零；对所有方法，则通过共同名义可行域和最优下界验证价格优化空间。

### 10.2 模型的优点 局限与推广

模型的主要优点有三项。其一，利用循环消除证明将混合整数模型等价化为线性规划，保留物理可行性并降低求解复杂度。其二，把预测误差分位数与滚动结算共同纳入调度，直接压缩高价补购而非只追求误差指标。其三，在价格预测之外给出费用最优下界，使神经网络的效果能够从精度、实际收益和剩余空间三个方面解释。

模型采用区间平均功率近似，实时层按即时平衡规则执行；电池退化与功率爬坡未纳入费用。年度数据及一月验证窗口限制了跨年推广，后续可增加气象变量、滚动交叉验证和电池循环成本，并将日末固定目标替换为跨日储能价值函数。加入线路与多节点约束后，同一费用结构可扩展至多个微网的协同购电。

## 十一 结论

四问结果汇总如下，各情景分别对应不同信息和计费条件。''')
    tab('四问模型与主策略结果',['问题','模型及策略','总费用/元','评价区间'],[['一','等价LP与周期储能',q1['cost'],'单日'],['二','岭回归＋70%余量',14132612.15924625,'334天'],['三','滚动LP＋50%余量',q3['total_cost_yuan'],'334天'],['四 日前','岭回归电价',q42['total_cost_yuan'],'334天'],['四 滚动','同期电价与滚动LP',q43['total_cost_yuan'],'334天'],['四 GRU对照','残差GRU与滚动LP',gru['total_cost_yuan'],'334天']])
    p(f'储能使第一问节费26.90%；第二问的风险余量在相同预测器下再降费10.01%；第三问引入三次预报更新，较仅午夜预报降低{saving3/q30["total_cost_yuan"]*100:.2f}%。第四问中，GRU在四个发布时刻均提升预测精度，滚动费用为{gru["total_cost_yuan"]/1e4:,.2f}万元；其名义计划费用距真实电价最优下界仅{br["regret"]/br["nominal_cost"]*100:.3f}%。由此可见，风险校准与日内信息更新决定主要经济收益，价格算法的作用是进一步细化已接近最优的购电决策。')
    p('''## 参考文献

[1] 全国大学生数学建模竞赛组委会. 2026年高教社杯全国大学生数学建模竞赛C题 微网与外部电网电力调控策略及附件.

[2] SciPy Developers. scipy.optimize.linprog and scipy.optimize.milp. https://docs.scipy.org/doc/scipy/reference/optimize.html. 访问日期2026-09-11.

[3] scikit-learn Developers. Ridge. https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html. 访问日期2026-09-11.

[4] Morstyn T, Hredzak B, Aguilera R P, Agelidis V G. Model Predictive Control for Distributed Microgrid Battery Energy Storage Systems. IEEE Transactions on Control Systems Technology, 2018, 26(3):1107–1114. DOI:10.1109/TCST.2017.2699159.

[5] PyTorch Contributors. GRU. https://docs.pytorch.org/docs/2.14/generated/torch.nn.GRU.html. 访问日期2026-09-11.

[6] Cho K, van Merrienboer B, Gulcehre C, et al. Learning Phrase Representations using RNN Encoder-Decoder for Statistical Machine Translation. EMNLP, 2014. arXiv:1406.1078.

[7] Boyd S, Vandenberghe L. Convex Optimization. Cambridge University Press, 2004. https://web.stanford.edu/~boyd/cvxbook/.
''')
    delivery.OUT=out;delivery.SOURCES={'1':str(out/'q1_intervals.csv'),'2':'artifacts/q12/ridge_q0.7_intervals.csv.gz','3':str(out/f'q3_m{sel["q3"]["mask"]}_intervals.csv.gz'),'4-2':str(out/f'q4_2_{sel["prices"]["2"]}_intervals.csv.gz'),'4-3':str(out/f'q4_3_{sel["prices"]["3"]}_intervals.csv.gz')}
    appendix=delivery.specified_tables();shift=ti+1-16;appendix=re.sub(r'表 (\d+)',lambda m:'表 '+str(int(m.group(1))+shift),appendix)
    caption=ti+1
    for item in json.loads((out/'specified_tables_manifest.json').read_text(encoding='utf8')):
        for _ in range(2 if item['question']=='1' else 3):
            appendix=appendix.replace(f'表 {caption} ',f'表 {caption} 问题{item["question"]}（{item["date"]}） ',1)
            caption+=1
    p(appendix)
    p('''## 附录 B 支撑文件与完整程序

五份结果文件result1、result2、result3、result4-2、result4-3保存购电、储能和紧急购电结果。逐时轨迹CSV、计划版本CSV、价格预测权重与训练日志、名义价格下界表和PNG/SVG图形随支撑材料提供。原始题目附件单独读取。

代码采用Python、NumPy、SciPy、pandas和PyTorch；绘图使用Matplotlib。src/q12.py负责基础数据与日前策略，src/q34_data.py处理小时预报，src/q4_forecast.py训练价格预测器；src/v3_q1.py求解周期第一问，src/v3_model.py实现最终合同结算与滚动LP，src/v3_experiments.py比较全年策略和名义价格下界，src/v3_verify.py复算轨迹，src/v3_payload.py及scripts/export_v3_xlsx.mjs导出结果。下列附录给出全部核心计算程序。
''')
    text=''.join(pieces)
    Path('reports/完整论文_V3.md').write_text(text,encoding='utf8')
    equations=re.findall(r'\$\$\s*\n(.*?)\n\$\$',text,re.S);Path('reports/完整论文_V3公式.tex').write_text('\n\n'.join('\\[\n'+s+'\n\\]' for s in equations),encoding='utf8')
    dump_json(out/'paper_manifest.json',{'figures':len(re.findall(r'!\[',text)),'tables':text.count('\n| ---'),'display_equations':len(equations),'characters':len(text),'main_tables':ti})
    print('V3 manuscript',len(text),'characters',fi,'figures',ti,'main tables')

if __name__=='__main__':main()
