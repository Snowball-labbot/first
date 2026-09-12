"""Verify V6 package fidelity, data fingerprints and figure exports."""
from pathlib import Path
import json,hashlib,zipfile,re
import numpy as np
import pandas as pd
from scipy.io import loadmat
from PIL import Image
import fitz
from lxml import etree
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    a=ROOT/'artifacts/v6';b=json.loads((a/'word_build.json').read_text(encoding='utf8'))
    assert sha(ROOT/'reports/完整论文_V6.docx')==b['docx_sha256']
    inv=json.loads((a/'source_inventory.json').read_text(encoding='utf8'))
    assert sha(ROOT/'reports/完整论文_V5.docx')==inv['docx_sha256']
    sources=json.loads((a/'figure_sources.json').read_text(encoding='utf8'))
    for p,h in sources['inputs'].items():assert sha(ROOT/p)==h,p
    d=loadmat(a/'figure_data.mat')
    imp=json.loads((ROOT/'artifacts/v5b/improvement.json').read_text())
    assert np.allclose(d['monthly_saving'].sum(axis=1)*10000,[r['saving'] for r in imp],rtol=0,atol=1e-6)
    assert np.allclose(d['final_cost'].ravel()*10000,[r['cost'] for r in imp],rtol=0,atol=1e-6)
    assert abs(d['q2_cost'][-1].sum()*10000-imp[0]['cost'])<1e-6
    assert abs(d['q3_evolution'].ravel()[-1]*10000-imp[1]['cost'])<1e-6
    assert d['price'].shape==(365,144) and d['price_mae'].shape==(3,4)
    assert np.all(d['price_mae'][2]<d['price_mae'][:2])
    figs={}
    for k,name in b['redrawn_figures'].items():
        paths={ext:ROOT/f'figures/v6/{name}.{ext}' for ext in ['png','svg','pdf','fig']}
        for p in paths.values():assert p.exists() and p.stat().st_size>500,p
        with Image.open(paths['png']) as im:
            dpi=im.info.get('dpi');assert dpi and min(dpi)>=300,(name,dpi)
            figs[name]={'width_px':im.width,'height_px':im.height,'dpi':dpi,'hashes':{e:sha(p) for e,p in paths.items()}}
        assert (ROOT/f'figures/v6/_qa/{name}_grayscale.png').exists()
        raw=json.loads((ROOT/f'figures/v6/{name}_audit.json').read_text(encoding='utf8'))
        figs[name]['matlab_layout_issues']=raw
    md=(ROOT/'reports/完整论文_V6.md').read_text(encoding='utf8')
    old=(ROOT/'reports/完整论文_V5.md').read_text(encoding='utf8')
    assert re.findall(r'\$\$(.*?)\$\$',md,re.S)==re.findall(r'\$\$(.*?)\$\$',old,re.S)
    assert [x for x in md.splitlines() if x.startswith('|')]==[x for x in old.splitlines() if x.startswith('|')]
    for p in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',md):assert (ROOT/'reports'/p).resolve().exists()
    for i in ['1','2','3','4-2','4-3']:assert (ROOT/f'artifacts/v5b/result{i}.xlsx').exists()
    result={'status':'PASS','checks':{'source_V5_unchanged':True,'input_fingerprints':len(sources['inputs']),
        'monthly_sums_match_selected_savings':True,'all_markdown_tables_and_formulas_identical':True,
        'all_Word_tables_math_styles_sections_preserved':b['all_equations_tables_and_sections_identical'],
        'figures_redrawn':len(figs),'figures_retained':6},'figures':figs,
        'delivery_workbooks':{i:{'path':f'artifacts/v5b/result{i}.xlsx','sha256':sha(ROOT/f'artifacts/v5b/result{i}.xlsx')} for i in ['1','2','3','4-2','4-3']},
        'docx_sha256':sha(ROOT/'reports/完整论文_V6.docx')}
    if (ROOT/'reports/完整论文_V6.pdf').exists():
        pdf=fitz.open(ROOT/'reports/完整论文_V6.pdf');texts=[p.get_text() for p in pdf]
        start=next(i+1 for i,t in enumerate(texts) if re.search(r'^附录\s*A\s+四问',t,re.M))
        assert '关键词' in texts[0] and '问题重述' in texts[1] and start-2<=30
        result['render']={'pages':len(pdf),'appendix_a_starts':start,'body_excluding_abstract':start-2,'pdf_sha256':sha(ROOT/'reports/完整论文_V6.pdf')}
        (ROOT/'.qa/v6/final_text.txt').write_text('\n'.join(f'PAGE {i+1}\n'+s for i,s in enumerate(texts)),encoding='utf8')
    (a/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['figures','delivery_workbooks']},ensure_ascii=False))
if __name__=='__main__':main()
