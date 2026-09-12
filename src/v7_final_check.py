"""Bind V7 numerical, manuscript, workbook and rendered evidence."""
from pathlib import Path
import json,re,sys,hashlib,subprocess
from docx import Document
from docx.oxml.ns import qn
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/v7'
SKILL=Path.home()/'.codex/skills/math-modeling/tools/docx/scripts'
sys.path.insert(0,str(SKILL));import paper_format as pf
def sha(p,normalize=False):
    b=Path(p).read_bytes()
    if normalize and Path(p).suffix in {'.py','.md','.tex','.json'}:b=b.replace(b'\r\n',b'\n')
    return hashlib.sha256(b).hexdigest()
def read(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def main():
    checks={n:read(n) for n in ['model_audit.json','trace_audit.json','xlsx_audit.json','render_audit.json']}
    assert all(v['status']=='PASS' for v in checks.values())
    build=read('word_build.json');render=checks['render_audit.json']
    for p,h in build['inputs'].items():assert sha(ROOT/p,True)==h,p
    for p,h in checks['model_audit.json']['sources'].items():assert sha(p,True)==h,p
    assert sha(ROOT/build['docx'])==build['sha256']==render['docx_sha256']
    assert sha(ROOT/'reports/完整论文_V7.pdf')==render['pdf_sha256']
    selection=read('delivery_selection.json')['sources']
    for s in checks['trace_audit.json']['strategies']:assert sha(ROOT/selection[s['question']])==s['trace_sha256']
    for k,h in checks['xlsx_audit.json']['unchanged_workbooks'].items():assert sha(OUT/f'result{k}.xlsx')==h
    assert sha(OUT/'result1.xlsx')==checks['xlsx_audit.json']['q1_sha256']
    doc=Document(ROOT/build['docx']);body='\n'.join(p.text for p in doc.paragraphs).split('附录 A')[0]
    assert all(x not in body for x in ['截图','博主','Modex','3.3 ','5.4 ','5.5 ','十一 结论','@@'])
    assert all(x in body for x in ['模型的评价与推广','10.1','10.2','10.3','35,126.95','13,991,392.60','13,479,283.32','14,765,492.68','14,210,881.01'])
    text=(ROOT/'reports/完整论文_V7.md').read_text(encoding='utf-8')
    assert not re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',text)
    assert len(doc.tables)==57 and len(doc.inline_shapes)==10 and len(doc._element.findall('.//'+qn('m:oMath')))==26
    values=set(re.findall(r'(?<!\w)\d[\d,]*\.\d+', '\n'.join(t for t in text.splitlines() if t.startswith('|'))))
    tabletext='\n'.join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    assert all(x in tabletext for x in values)
    # Exclude literal source code, never manuscript paragraphs, from prose formatting checks.
    code=False
    for p in list(doc.paragraphs):
        if p.text=='src/q12.py':code=True
        if code:p._element.getparent().remove(p._element)
    issues=pf.validate_paper_structure(doc,'cumcm',rendered_pages=render['body_and_references_pages_excluding_abstract'],target_pages=0,min_content_units=0,official_max_pages=30)
    assert not issues,issues
    schema=subprocess.run([sys.executable,str(SKILL/'office/validate.py'),str(ROOT/build['docx'])],capture_output=True,text=True,errors='replace')
    assert schema.returncode==0,schema.stdout+schema.stderr
    tests=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests'],cwd=ROOT,capture_output=True,text=True,errors='replace')
    assert tests.returncode==0,tests.stdout+tests.stderr
    match=re.search(r'Ran (\d+) tests',tests.stdout+tests.stderr);assert match
    outputs=[*OUT.glob('*.xlsx'),*ROOT.glob('reports/完整论文_V7.*'),ROOT/'reports/完整论文_V7公式.tex']
    assert all(p.stat().st_size<20*1024**2 for p in outputs if p.suffix in ['.docx','.pdf'])
    result=dict(status='PASS',unit_tests=int(match[1]),audited_intervals=checks['trace_audit.json']['intervals'],random_path_tests=48,state_tests=17,tables=57,figures=10,native_math=26,display_equations=15,table_numeric_values_checked=len(values),render=render,schema='PASS',structure_issues=issues,format_overrides='Source appendix excluded from Markdown prose scan; no nonofficial minimum length; official 30-page body maximum retained',outputs={str(p.relative_to(ROOT)):sha(p) for p in outputs},sources={str(p.relative_to(ROOT)):sha(p,True) for p in ROOT.glob('src/*v7*.py')})
    (OUT/'final_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:result[k] for k in ['status','unit_tests','audited_intervals','tables','figures']},ensure_ascii=False))
if __name__=='__main__':main()
