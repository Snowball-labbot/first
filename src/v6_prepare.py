"""Export immutable V5 evidence to MATLAB, and inventory the retained template."""
from pathlib import Path
import json,re,hashlib,zipfile
import numpy as np
import pandas as pd
import scipy.io
import fitz
from lxml import etree
from src.q34_data import read_extended

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    out=ROOT/'artifacts/v6';out.mkdir(exist_ok=True)
    qa=ROOT/'.qa/v6';qa.mkdir(parents=True,exist_ok=True)
    source=ROOT/'reports/完整论文_V5.docx'
    z=zipfile.ZipFile(source)
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
    tree=etree.fromstring(z.read('word/document.xml'))
    rels={a.get('Id'):a.get('Target') for a in etree.fromstring(z.read('word/_rels/document.xml.rels'))}
    images=[]
    for i,p in enumerate(tree.findall('w:body/w:p',ns)):
        for b in p.findall('.//a:blip',ns):
            rid=b.get('{'+ns['r']+'}embed')
            images.append({'paragraph':i,'rid':rid,'part':'word/'+rels[rid],
                           'extent':[dict(e.attrib) for e in p.findall('.//wp:extent',ns)]})
    inventory={'source':str(source),'docx_sha256':sha(source),'images':images,
        'package':{n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()},
        'sections':[etree.tostring(s).decode() for s in tree.findall('.//w:sectPr',ns)]}
    (out/'source_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf8')
    (qa/'artifact.md').write_text(
        '# V6 template contract\nReference: '+str(source)+'\nSHA256: '+sha(source)+
        '\nKeep the existing 87-page V5 Word package. A4, horizontal margins 2.6 cm, vertical 2.54 cm; preserve actual section XML, styles, headers, footers, all tables and native math verbatim.'
        '\nEditable slots: selected image binary parts (same relationships), associated extents preserving width, selected prose and captions; no heading or table renumbering. Plain text replacements preserve paragraph/run properties. All other package parts must remain byte-identical.'
        '\nPage patterns: title/abstract page; numbered body sections with equations and three-line tables; Appendix A specified dates; Appendix B complete code. Preserve all 49 math objects and 63 tables. V5 PDF is the reference render; source inventory holds per-part hashes and the 16 figure slots.'
        '\nFidelity gate: full new render, compare section/style/header/table/math XML; every new figure read at final size; retain exact V5 source hash.\n',encoding='utf8')
    data,audit=read_extended(ROOT.parent/'CUMCM2026Problems/C题')
    d={'price':data['actual_price'],'days':np.arange(1,366),'hours':np.arange(144)/6}
    q1=pd.read_csv(ROOT/'artifacts/v3/q1_intervals.csv')
    qs=json.loads((ROOT/'artifacts/v3/q1_summary.json').read_text())
    sens=pd.read_csv(ROOT/'artifacts/v3/q1_efficiency.csv')
    d['q1_cost']=np.array([qs['no_storage_cost'],qs['cost'],sens.loc[(sens.roundtrip_efficiency-.9).abs()<1e-8,'cost'].iloc[0]])/1e4
    q2=json.loads((ROOT/'artifacts/q12/q2_summary.json').read_text())['strategies']
    improvements=json.loads((ROOT/'artifacts/v5b/improvement.json').read_text())
    d['q2_cost']=np.array([[s['normal_cost_yuan'],s['emergency_cost_yuan']] for s in q2]+[[improvements[0]['after']['original_cost_yuan'],improvements[0]['after']['emergency_cost_yuan']]])/1e4
    ms=pd.read_csv(ROOT/'artifacts/v5b/monthly_savings.csv')
    d['monthly_saving']=np.array([ms.loc[ms.question.astype(str)==k,'saving'].values for k in ['2','3','4-2','4-3']])/1e4
    sums={s['strategy']:s for s in json.loads((ROOT/'artifacts/v3/summary.json').read_text())}
    d['q3_cost']=np.array([sums[f'q3_m{i}']['total_cost_yuan'] for i in range(8)])/1e4
    d['q3_evolution']=np.array([sums['q3_m7']['total_cost_yuan'],improvements[1]['baseline_cost'],improvements[1]['cost']])/1e4
    d['q3_validation']=pd.read_csv(ROOT/'artifacts/v3/q3_validation.csv').pivot(index='q',columns='mask',values='cost').to_numpy()/1e4
    d['q4_cost']=np.array([[sums[f'q4_{mode}_{m}']['total_cost_yuan'] for m in ['seasonal','ridge','gru_mean','oracle']] for mode in [2,3]])/1e4
    metrics=pd.read_csv(ROOT/'artifacts/v2/price_errors_by_issue.csv')
    d['price_mae']=np.array([metrics.loc[metrics.model==m,'mae'].values for m in ['seasonal','ridge','gru_mean']])
    bounds=pd.read_csv(ROOT/'artifacts/v3/nominal_price_bound.csv')
    d['bound_daily']=np.array([bounds[bounds.model==m].regret.values for m in ['seasonal','ridge','gru_mean']])/1e4
    d['bound_nominal']=bounds.groupby('model').nominal_cost.sum().loc[['seasonal','ridge','gru_mean']].to_numpy()/1e4
    d['saving']=np.array([r['saving'] for r in improvements])/1e4
    d['saving_ci']=np.array([[next(b for b in r['bootstrap'] if b['block']==14)[k] for k in ['low','high']] for r in improvements])/1e4
    d['final_cost']=np.array([r['cost'] for r in improvements])/1e4
    validation=pd.read_csv(ROOT/'artifacts/q12/policy_validation.csv')
    d['validation_cost']=np.array([validation.loc[validation.forecast==m,'cost_yuan'].values for m in ['seasonal','ridge']])/1e4
    d['validation_emergency']=np.array([validation.loc[validation.forecast==m,'emergency_cost_yuan'].values for m in ['seasonal','ridge']])/1e4
    d['q2_validation_columns']=np.array(validation.columns,dtype=object)
    # Raw full-resolution input remains archived; quantiles/means are descriptive aggregation.
    assert d['price'].shape==(365,144) and np.isfinite(d['price']).all()
    for k,v in d.items():
        if isinstance(v,np.ndarray) and v.dtype.kind not in 'OU':assert np.isfinite(v).all(),k
    scipy.io.savemat(out/'figure_data.mat',d)
    sources=['reports/完整论文_V5.docx','reports/完整论文_V5.md','reports/完整论文_V5.pdf',
        'artifacts/v3/q1_summary.json','artifacts/v3/q1_efficiency.csv','artifacts/q12/q2_summary.json',
        'artifacts/v3/summary.json','artifacts/v3/q3_validation.csv','artifacts/v2/price_errors_by_issue.csv',
        'artifacts/v3/nominal_price_bound.csv','artifacts/v5b/improvement.json','artifacts/v5b/monthly_savings.csv','artifacts/q12/policy_validation.csv']
    (out/'figure_sources.json').write_text(json.dumps({'inputs':{s:sha(ROOT/s) for s in sources},'raw_input_audit':audit,
        'aggregation':'Daily/monthly descriptive statistics only; no clipping, smoothing, deleted values or refitting.',
        'base_commit':'6ea382b','price_range':[float(d['price'].min()),float(d['price'].max())]},ensure_ascii=False,indent=2),encoding='utf8')
    modex=fitz.open('D:/内容/xwechat_files/wxid_fzz37iqypd3y32_4403/msg/file/2026-09/26CModex4.8+5直出.pdf')
    for i in [1,2,3]:modex[i].get_pixmap(matrix=fitz.Matrix(1,1)).save(str(qa/f'modex_{i+1}.png'))
    print('Prepared MATLAB evidence, template inventory and reference pages.')
if __name__=='__main__':main()
