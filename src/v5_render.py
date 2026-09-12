"""Render the final Word with native Word, then render the same PDF with PyMuPDF."""
from pathlib import Path
import hashlib
import json
import re
import pymupdf as fitz
import win32com.client
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]

def main():
    source=ROOT/'reports/完整论文_V5.docx';dest=ROOT/'reports/完整论文_V5.pdf'
    qa=ROOT/'.qa/v5/render';qa.mkdir(parents=True,exist_ok=True)
    app=win32com.client.DispatchEx('Word.Application');app.Visible=False;app.DisplayAlerts=0;doc=None
    try:
        app.AutomationSecurity=3
        doc=app.Documents.Open(str(source),ReadOnly=True,AddToRecentFiles=False)
        doc.Repaginate();word_pages=doc.ComputeStatistics(2)
        doc.ExportAsFixedFormat(str(dest),17)
    finally:
        if doc is not None:doc.Close(False)
        app.Quit()
    pdf=fitz.open(dest);pages=[p.get_text() for p in pdf]
    assert len(pdf)==word_pages
    appendix_a=next(i+1 for i,t in enumerate(pages) if re.search(r'^附录\s*A\s+四问',t,re.M))
    assert '关键词' in pages[0] and '问题重述' in pages[1]
    assert appendix_a-2<=30
    images=[]
    for i,p in enumerate(pdf):
        pix=p.get_pixmap(matrix=fitz.Matrix(1.35,1.35));filename=qa/f'page-{i+1:02d}.png';pix.save(filename);images.append(filename)
    for start in range(0,len(images),12):
        sheet=Image.new('RGB',(4*310,3*455),'#dedede');draw=ImageDraw.Draw(sheet)
        for j,path in enumerate(images[start:start+12]):
            with Image.open(path) as im:
                im.thumbnail((300,425));x=(j%4)*310+5;y=(j//4)*455+23;sheet.paste(im,(x,y));draw.text((x,y-19),f'Page {start+j+1}',fill='black')
        sheet.save(qa/f'contact-{start//12+1}.jpg')
    (qa/'text.txt').write_text('\n'.join(f'--- PAGE {i+1} ---\n{t}' for i,t in enumerate(pages)),encoding='utf-8')
    result={'status':'PASS','backend':'Microsoft Word native PDF + PyMuPDF','pages':len(pdf),'abstract_pages':1,'appendix_a_starts':appendix_a,'body_and_references_pages_excluding_abstract':appendix_a-2,'pages_before_appendix':appendix_a-1,'docx_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'pdf_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'all_pages_rasterized':len(images)}
    (ROOT/'artifacts/v5/render_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
