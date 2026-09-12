"""Patch the retained V5 Word package; preserve styles, tables, math and template."""
from pathlib import Path
import json,re,hashlib,zipfile,difflib
from lxml import etree
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'm':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
def norm(s):return re.sub(r'\s+','',s.replace('**',''))
def digest(b):return hashlib.sha256(b).hexdigest()
def retext(p,new):
    nodes=p.findall('.//w:t',NS);old=''.join(n.text or '' for n in nodes)
    starts=[];pos=0
    for n in nodes:starts.append(pos);pos+=len(n.text or '')
    result=['']*len(nodes)
    def owner(i):
        for k in range(len(starts)-1,-1,-1):
            if i>=starts[k]:return k
        return 0
    for op,a,b,c,d in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
        if op=='equal':
            for i in range(a,b):result[owner(i)]+=old[i]
        elif op in ['insert','replace']:result[owner(a)]+=new[c:d]
    for n,t in zip(nodes,result):n.text=t;n.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    assert ''.join(n.text or '' for n in nodes)==new

def main():
    out=ROOT/'artifacts/v6';source=ROOT/'reports/完整论文_V5.docx'
    inv=json.loads((out/'source_inventory.json').read_text(encoding='utf8'))
    assert digest(source.read_bytes())==inv['docx_sha256']
    md=(ROOT/'reports/完整论文_V5.md').read_text(encoding='utf8');changes=[]
    def rev(prefix,new):
        nonlocal md
        matches=[p for p in md.split('\n\n') if p.startswith(prefix)]
        assert len(matches)==1,(prefix,len(matches))
        old=matches[0];md=md.replace(old,new,1);changes.append({'old':old,'new':new})
    rev('11条全年候选轨迹通过','11条全年候选轨迹通过物理约束与合同账单复核，四组节费对照均保持相同初末库存。结果表明，风险校准确定合理购电规模，滚动预报降低供需偏差，库存价值控制将有限电量配置给更昂贵的后续缺口，三者共同提升微网运行经济性。')
    rev('数据核查结果为：','数据核查表明：附件1含60个时间类型单元格和84个字符串，统一转换后得到完整时间序列；附件2两类序列均无缺失、非有限值、负数、重复日期或完全重复日曲线。全局四分位距检验未检出超界观测，原始样本全部保留。')
    rev('附件未提供测量误差分布','原始供需和调度轨迹保留十分钟分辨率。图中的月均值、分位范围和累计费用均由原始记录直接汇总，分别刻画季节结构、价格分布与策略收益。')
    rev('各路径内的递推使用','各历史路径的后续费用经递推后取均值，形成当前库存的续期价值估计；执行动作由当前真实供需和这一价值函数共同决定。1月验证中，零终端价值与低谷价终端价值均得到509,140.53元，较即时平衡节省616.94元，按预设候选顺序选取零终端价值。')
    rev('图 5 比较无余量','图 5将普通计划费与紧急费置于同一费用平面，虚线为总费用等值线，点旁数字为误差余量分位数。沿各预测器的四个候选增加余量，紧急支出下降而普通支出上升；圈出的岭回归70%余量方案取得最低验证总费。')
    rev('策略费用分解如图 7','表 7列出基础策略，图 7按实际替换顺序展示从同期无余量到岭回归预测、70%风险余量及库存价值控制的费用变化。每一步均与前一步配对，直接给出各层改进的费用贡献。')
    rev('图 7 第二问四组策略','图 7 第二问逐层优化的费用变化与节费来源')
    rev('蓝色为普通计划购电费','图 7的折线按模型实际替换顺序连接四个策略，末端为最终库存价值控制方案；下方分别列出预测改善、风险校准和库存配置带来的节省。各组件的费用贡献由相邻策略的同条件比较确定，体现预测、风险与控制的协同作用。')
    rev('图 4 第一问储能收益','图 4 储能往返效率与最优购电费用的关系')
    rev('图 4 对比无储能','图 4给出五组往返效率下的最优费用，并以无储能费用为参照。储能降低购电支出，效率提升进一步减少能量转移损耗；主结果采用两侧各90%、即往返81%的效率。')
    rev('在相同岭回归、70%余量','在相同岭回归、70%余量、费用规则和初始储电量下，历史路径价值控制使334天费用由14,132,612.16元降至13,991,392.60元，节省141,219.56元（0.999%）。其中紧急购电费减少141,170.39元，而紧急电量由197,465.10增至198,137.46 kWh。由此可见，收益来自补购与放电时点的重新分配：以较低价格补足当前缺口，将库存留给更高价格的后续缺口。两方案期末均为5,903.65 kWh，库存转移的经济收益得到同状态对照支持。')
    rev('负载同槽七日相关系数','负载同槽七日相关系数为0.9855，日总量七日相关为0.9880，周周期特征具有明确的数据依据。28、56、60、84日训练窗的固定控制器敏感性费用分别为14,211,345.15、14,152,541.05、14,132,612.16、14,033,154.46元，说明窗口长度通过历史信息量与时效性共同影响预测。四种窗口在一月短历史下的验证结果相同，主方案保留60日窗，其余结果用于检验窗口敏感性。')
    rev('图 9左侧以一月验证费用','图 9以一月验证数据比较风险余量与更新时间。左图给出24组候选的费用矩阵，黑框标出50%余量、三次日内更新的选定方案；右图沿0、6、12、18点的顺序增加预报，展示信息更新对验证费用的影响。')
    rev('图 9 风险余量选择','图 9 风险余量与预报更新频次的验证比较')
    rev('图 10 八种更新时间','图 10 预报更新组合的全年收益与第三问最终费用')
    rev('图 10展示同一','图 10在同一50%余量下比较八种更新时间组合。左侧蓝格表示启用该时刻预报，右侧条形给出相对仅午夜预报的全年节费；下方汇总基础滚动、负载选择与库存价值控制的最终费用。')
    rev('图 11 全年实际电价','图 11 全年电价的时刻结构与月度分布')
    rev('图 11展示日均','图 11展示全年电价的日内结构与月度分布。峰谷时段决定储能转移方向，价格幅度及季节变化影响各时段购电规模。')
    # Replace the nearest description if present; explicitly define quantile whiskers.
    rev('同期预测取昨日','图 11a以十分钟原始记录展示电价的日内峰谷及季节差异，颜色表示电价，范围覆盖全部观测。图 11b的点为各月均价，线段为该月全部十分钟电价的10%—90%分位范围，表示分布离散程度。\n\n同期预测取昨日与上周同目标区间价格的平均值。岭回归在这两组历史价格、日历周期特征及滞后统计量上构造12维输入。残差GRU使用6维输入：昨日价、上周价、日内正余弦和星期正余弦。三类预测器共享历史可见范围，分别表达周期基线、线性修正与非线性时序依赖。')
    rev('图 13 GRU与非神经网络','图 13 四个发布时刻的价格预测MAE')
    rev('图 15展示相对同期价格预测','图 15a、b在相同基础执行器内比较价格预测器的节费贡献，零点右侧为节省、左侧为增费。图 15c、d进一步给出库存价值控制相对各自即时平衡基线的月度节费及全年区间，将预测模块和执行模块的经济作用分别呈现。')
    rev('图 15 价格预测器对实际','图 15 价格预测与库存价值控制的费用贡献')
    rev('价格误差降低与电费下降','GRU改善了四个发布时刻的价格预测精度，其费用贡献取决于预测修正是否改变可行调度动作。固定基础滚动执行器后，GRU相对同期节省2,094.78元，配对区块重采样区间跨零；因此按一月验证费用保留原价格模型，并在执行层引入库存价值控制。图 15d采用2,000次、14天配对区块重采样，点为全年节费，线为95%区间；四个分支分别比较，不叠加为同一系统收益。最终费用见表 13。')
    rev('图 16汇总334个','图 16a累计334个共同名义可行域上的逐日最优值差距，图 16b汇总全年剩余改进上限。GRU的名义费用距真实电价最优值13.68万元，占其名义费用1.002%；在既定供需预测和储能约束下，进一步提高价格预测精度的费用改善空间已接近这一量级。')
    rev('图 16 价格预测的名义','图 16 价格预测的累计名义差距与剩余改进上限')
    rev('表 13 汇总交付结果。','表 13汇总四问交付结果及库存价值控制增益。基础列与改进列采用相同费用规则和初末库存；图 7、图 10及图 15共同展示最终方案、收益来源和月份分布，指定日期的购电及储能结果见附录A。')
    rev('确定性调度费用为','第一问通过LP与连续DP得到一致的最优费用35,126.85元，确立确定性调度基准。第二问结合风险校准与库存价值控制，将全年费用降至13,991,392.60元；第三问进一步利用日内预报、负载选择与调单机会，费用降至13,479,283.32元。波动电价下，日前与滚动费用分别为14,765,492.68元和14,210,881.01元。四问结果共同表明，微网优化的关键在于根据后续缺口价格和合同调整机会配置库存，并以完整购电账单评价信息与控制的价值。')
    figures={1:'modeling_overview',4:'q1_efficiency',5:'q2_validation',7:'q2_cost',9:'q3_validation',
             10:'q3_updates',11:'annual_price',13:'q4_accuracy',15:'q4_cost',16:'q4_bound'}
    original_paths=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',md)
    for num,name in figures.items():md=md.replace(original_paths[num-1],f'../figures/v6/{name}.png')
    # Apply whole-paragraph edits. A replacement containing a paragraph break is
    # inserted as one paragraph in Word to retain the template's existing slots.
    with zipfile.ZipFile(source) as z:parts={n:z.read(n) for n in z.namelist()}
    tree=etree.fromstring(parts['word/document.xml'])
    paras=tree.findall('w:body/w:p',NS)
    for c in changes:
        target=[p for p in paras if norm(''.join(p.itertext()))==norm(c['old'])]
        if not target:
            target=[p for p in paras if norm(''.join(p.xpath('.//w:t/text()',namespaces=NS)))==norm(c['old'])]
        assert len(target)==1,(c['old'][:60],len(target))
        assert not target[0].findall('.//m:oMath',NS),'Do not rewrite math'
        retext(target[0],c['new'].replace('\n\n',''))
    for num,name in figures.items():
        info=inv['images'][num-1];path=ROOT/f'figures/v6/{name}.png'
        parts[info['part']]=path.read_bytes()
        p=paras[info['paragraph']]
        if num in (5,7):
            # Separate the adjacent table rule from the plot without changing
            # the retained template styles, table XML or figure width.
            pr=p.find('w:pPr',NS)
            if pr is None:pr=etree.SubElement(p,'{'+NS['w']+'}pPr');p.insert(0,pr)
            spacing=pr.find('w:spacing',NS)
            if spacing is None:spacing=etree.SubElement(pr,'{'+NS['w']+'}spacing')
            spacing.set('{'+NS['w']+'}before','120')
        with Image.open(path) as im:ratio=im.height/im.width
        for e in p.findall('.//wp:extent',NS):e.set('cy',str(round(int(e.get('cx'))*ratio)))
        for e in p.findall('.//a:xfrm/a:ext',NS):e.set('cy',str(round(int(e.get('cx'))*ratio)))
    parts['word/document.xml']=etree.tostring(tree,xml_declaration=True,encoding='UTF-8',standalone=True)
    final=ROOT/'reports/完整论文_V6.docx'
    with zipfile.ZipFile(final,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for n,b in parts.items():z.writestr(n,b)
    (ROOT/'reports/完整论文_V6.md').write_text(md,encoding='utf8')
    equations=re.findall(r'\$\$\s*\n(.*?)\n\$\$',md,re.S)
    (ROOT/'reports/完整论文_V6公式.tex').write_text('\n\n'.join('\\[\n'+s+'\n\\]' for s in equations),encoding='utf8')
    changed=[n for n,b in parts.items() if digest(b)!=inv['package'][n]]
    allowed={'word/document.xml',*[inv['images'][i-1]['part'] for i in figures]}
    assert set(changed)==allowed
    oldtree=etree.fromstring(zipfile.ZipFile(source).read('word/document.xml'))
    for tag in ['w:tbl','m:oMath','w:sectPr']:
        assert [etree.tostring(x) for x in oldtree.findall('.//'+tag,NS)]==[etree.tostring(x) for x in tree.findall('.//'+tag,NS)],tag
    assert digest(source.read_bytes())==inv['docx_sha256']
    result={'status':'PASS','source_commit':'6ea382b','docx_sha256':digest(final.read_bytes()),
        'source_sha256':inv['docx_sha256'],'changed_parts':changed,'preserved_tables':len(tree.findall('.//w:tbl',NS)),
        'preserved_math':len(tree.findall('.//m:oMath',NS)),'native_numbered_equations':len(equations),
        'figures':16,'redrawn_figures':figures,'unchanged_template_parts':len(parts)-len(changed),
        'editorial_paragraphs':len(changes),'all_equations_tables_and_sections_identical':True}
    (out/'word_build.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    (out/'editorial_changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
