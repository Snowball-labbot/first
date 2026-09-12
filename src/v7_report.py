"""Render source-backed V7 manuscript tables and requested-date appendix."""
from pathlib import Path
import re,json
import pandas as pd
from src.q12 import dump_json
from src.v5_report import tab
from src.v7_delivery import SOURCES
from src.deliver_q12 import blocks
import src.v2_delivery as delivery
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/v7'
def main():
    text=(ROOT/'reports/V7正文源稿.md').read_text(encoding='utf-8')
    parameters=tab('1','储能参数及离散时段',['参数','数值','说明'],[
        ['额定容量','12,000 kWh','题设'],['允许储电量','1,200—10,800 kWh','题设'],['最大充放电功率','5,000 kW','母线侧'],
        ['初始储电量','6,000 kWh','1月1日零点'],['充电／放电效率','0.9／0.9','分别计入'],['时段长度','1/6 h','十分钟']])
    symbols=tab('2','主要符号',['符号','含义','单位'],[
        ['$L_t,V_t$','负载电量、光伏电量','kWh'],['$g_t,e_t$','普通购电量、紧急购电量','kWh'],['$c_t,d_t,w_t$','充电、放电、弃电','kWh'],
        ['$S_t$','时段开始的内部储电量','kWh'],['$p_t$','外网交易电价','元/kWh'],['$M$','单时段母线侧充放电上限','kWh'],
        ['$x_t,y_t$','午夜合同、最终有效合同','kWh'],['$u_t,v_t$','取消量、新增量','kWh'],[r'$J_t(s),\bar J_t(s)$','后续费用、场景平均后续费用','元'],
        [r'$\mu_t(s)$','每单位内部库存的边际价值','元/kWh'],[r'$\mathcal I_\tau$','发布时刻可获得的信息','—']])
    f=pd.read_csv(SOURCES['1']);q1=[]
    for slots in [[60,72,84],[96,108,120]]:
        row=[]
        for i in slots:row.extend([f.interval.iloc[i],float(f.plan_kwh.iloc[i])])
        q1.append(row)
    q1.append(['全天购电量',float(f.plan_kwh.sum()),'全天购电费',float((f.price*f.plan_kwh).sum()),'—','—'])
    q1text=tab('3','第一问指定时段购电及全天费用',['时间段','购电量']*3,q1)
    b=blocks(f);rows=[[*b[i],*b[i+1]] for i in range(0,6,2)];rows.append(['00:00储电量',6000.,'—','24:00储电量',6000.,'—'])
    q1text+=tab('4','第一问四小时充放电及首末库存',['时间段','充电量','放电量']*2,rows)
    gains={r['question']:r for r in json.loads((ROOT/'artifacts/v5b/improvement.json').read_text(encoding='utf-8'))}
    g=gains['2'];q2=tab('5','第二问执行策略的费用与库存',['指标','即时放电','库存价值控制'],[
        ['普通计划费/元',g['before']['original_cost_yuan'],g['after']['original_cost_yuan']],['紧急购电费/元',g['before']['emergency_cost_yuan'],g['after']['emergency_cost_yuan']],
        ['总费用/元',g['baseline_cost'],g['cost']],['紧急电量/kWh',g['before']['emergency_kwh'],g['after']['emergency_kwh']],['期末库存/kWh',g['final_soc'],g['final_soc']]])
    g=gains['3'];q3=tab('6','第三问最终方案的费用构成',['费用项目','金额/元'],[
        ['午夜原合同',g['after']['original_cost_yuan']],['新增合同费用',g['after']['increase_cost_yuan']],['取消合同半价抵扣',g['after']['decrease_cost_yuan']],['紧急购电',g['after']['emergency_cost_yuan']],['总费用',g['cost']]])
    final=tab('7','四问最终费用与运行区间',['问题','总费用/元','运行区间'],[
        ['一',float((f.price*f.plan_kwh).sum()),'单日'],*[[k,gains[k]['cost'],'334天'] for k in ['2','3','4-2','4-3']]])
    for key,value in [('PARAMETERS',parameters),('SYMBOLS',symbols),('Q1_TABLES',q1text),('Q2_COST',q2),('Q3_LEDGER',q3),('FINAL_RESULTS',final)]:text=text.replace('@@'+key+'@@',value.rstrip())
    delivery.OUT=OUT;delivery.SOURCES=SOURCES;appendix=delivery.specified_tables();caption=16
    for item in json.loads((OUT/'specified_tables_manifest.json').read_text(encoding='utf-8')):
        for _ in range(2 if item['question']=='1' else 3):
            appendix=appendix.replace(f'表 {caption} ',f'表 {caption} 问题{item["question"]}（{item["date"]}） ',1);caption+=1
    appendix=re.sub(r'表 (\d+)',lambda m:'表 '+str(int(m[1])-8),appendix)
    ending='''## 附录 B 支撑文件与计算程序

支撑文件包括result1.xlsx、result2.xlsx、result3.xlsx、result4-2.xlsx、result4-3.xlsx五份结果表，逐时供需与储能轨迹、价格预测及模型参数，以及以下完整计算程序。结果表保留现有布局；第一问为周期运行，按原模板区间起点映射同一日轨迹，末行次日00:00—00:10对应重复日首区间。

原始附件只读。程序依次完成数据读取、预测、风险校准、计划优化、实时执行及结果输出；时间和单位转换在输入阶段统一完成。完整运行说明随支撑文件提供。
'''
    text+='\n\n'+appendix+'\n\n'+ending
    assert '@@' not in text
    eq=re.findall(r'\$\$(.*?)\$\$',text,re.S);tables=re.findall(r'^表 (\d+) [^\n]+\n\n\|',text,re.M);figs=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',text)
    assert list(map(int,tables))==list(range(1,58)),tables
    (ROOT/'reports/完整论文_V7.md').write_text(text,encoding='utf-8');(ROOT/'reports/完整论文_V7公式.tex').write_text('\n\n'.join(eq),encoding='utf-8')
    dump_json(OUT/'paper_manifest.json',dict(tables=len(tables),main_tables=7,figures=len(figs),display_equations=len(eq),characters=len(text),figure_paths=figs))
    print('V7 manuscript',len(text),'characters',len(tables),'tables',len(figs),'figures',len(eq),'display equations')
if __name__=='__main__':main()
