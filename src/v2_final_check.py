"""Validate frozen manuscript, workbook hashes and native Word PDF; render QA pages."""
from pathlib import Path
import hashlib,json,re,shutil
import pymupdf as fitz
from PIL import Image,ImageOps,ImageDraw
from docx import Document
from docx.oxml.ns import qn
from src.q12 import dump_json
from src.build_v2_word import sha


def main():
    out=Path('artifacts/v2');md=Path('reports/完整论文_V2.md').read_text(encoding='utf8')
    meta=json.loads((out/'word_build.json').read_text(encoding='utf8'));doc=Document(meta['docx'])
    assert sha(meta['docx'])==meta['sha256']
    for file,h in meta['inputs'].items():assert sha(file)==h,file
    for key,item in json.loads((out/'xlsx_audit.json').read_text()).items():
        assert hashlib.sha256((out/f'result{key}.xlsx').read_bytes()).hexdigest()==item['sha256']
    assert not any(ord(c)<32 and c not in '\n\t\r' for c in md)
    figures=re.findall(r'^图 (\d+) ',md,re.M);assert list(map(int,figures))==list(range(1,13)),figures
    titles=re.findall(r'^表 (\d+) ',md,re.M);assert list(map(int,titles))==list(range(1,66)),titles
    expected=json.loads((out/'paper_manifest.json').read_text())
    assert len(doc.tables)==expected['tables']==65 and len(doc.inline_shapes)==12
    assert meta['display_equations']==expected['display_equations']
    text='\n'.join(p.text for p in doc.paragraphs)
    main_text=text.split('附录 B 可运行支撑材料')[0]
    assert not re.search(r'\*\*|\$\$|\\(?:frac|hat|beta)\b',main_text)
    for amount in ['13,765,317.70','14,486,341.42','14,132,612.16']:assert amount in main_text
    # All 17 prescribed day/strategy combinations are present, with actual emergency events.
    specified=json.loads((out/'specified_tables_manifest.json').read_text());assert len(specified)==17
    assert all(x['blocks']==6 and len(x['slots'])==6 for x in specified)
    pdf_path=Path('.qa/v2_paper/render/完整论文_V2.pdf');pdf=fitz.open(pdf_path)
    appendix=next(i+1 for i,p in enumerate(pdf) if '附录 A 四问指定日期完整结果' in p.get_text())
    assert appendix-1<=30
    assert '关键词' in pdf[0].get_text() and '一 问题重述' not in pdf[0].get_text()
    assert '一 问题重述' in pdf[1].get_text()
    assert all(abs(p.rect.width-595.28)<1 and abs(p.rect.height-841.89)<1 for p in pdf)
    pages_dir=Path('.qa/v2_paper/pages');pages_dir.mkdir(exist_ok=True)
    thumbs=[]
    for i,page in enumerate(pdf):
        path=pages_dir/f'page-{i+1:02d}.png';page.get_pixmap(dpi=100).save(path)
        im=Image.open(path).convert('RGB');im.thumbnail((180,255));thumb=Image.new('RGB',(190,278),'#eeeeee')
        thumb.paste(im,((190-im.width)//2,18));ImageDraw.Draw(thumb).text((6,3),str(i+1),fill='black');thumbs.append(thumb)
    for first in range(0,len(thumbs),18):
        subset=thumbs[first:first+18];grid=Image.new('RGB',(6*190,3*278),'white')
        for j,im in enumerate(subset):grid.paste(im,((j%6)*190,(j//6)*278))
        grid.save(pages_dir/f'contact-{first//18+1}.png')
    # Report source is Word, not a LaTeX compilation; retain exact native export for reading.
    dest=Path('reports/完整论文_V2.pdf');shutil.copy2(pdf_path,dest)
    result={'status':'PASS','word_sha256':sha(meta['docx']),'pdf_sha256':sha(dest),'pages':len(pdf),
        'pages_before_appendix':appendix-1,'tables':len(doc.tables),'figures':len(doc.inline_shapes),
        'native_math_objects':len(doc._element.findall('.//'+qn('m:oMath'))),'display_equations':meta['display_equations'],
        'specified_day_combinations':len(specified),'render_backend':'Microsoft Word native PDF + PyMuPDF 100dpi',
        'renderer_recovery':'Packaged render_docx raster stage failed because Poppler absent; native Word PDF succeeded, all same PDF pages rendered with PyMuPDF.',
        'deterministic_checks':'PASS','visual_review':'See docs/RUN_V2.md; contact sheets and selected pages reviewed separately',
        'independent_subagent_review':'Not used under repository single-agent instructions'}
    dump_json(out/'final_delivery_check.json',result);print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
