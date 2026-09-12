"""Export Word natively and render all pages for visual QA."""
from pathlib import Path
import sys,json
import fitz,win32com.client
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from src.v9_inventory import sheets
out=root/'.qa/v9/final';out.mkdir(parents=True,exist_ok=True)
app=win32com.client.DispatchEx('Word.Application');app.Visible=False;app.DisplayAlerts=0;app.AutomationSecurity=3;doc=None
try:
 print('Opening V9',flush=True);doc=app.Documents.Open(str(root/'reports/完整论文_V9.docx'),ReadOnly=True,AddToRecentFiles=False)
 doc.Repaginate();print('Exporting PDF',flush=True);doc.ExportAsFixedFormat(str(root/'reports/完整论文_V9.pdf'),17)
finally:
 if doc is not None:doc.Close(False)
 app.Quit()
p=fitz.open(root/'reports/完整论文_V9.pdf');paths=[];stats=[]
for i,page in enumerate(p):
 path=out/f'page-{i+1:02d}.png';page.get_pixmap(matrix=fitz.Matrix(1.4,1.4)).save(path);paths.append(path)
 stats.append(dict(page=i+1,characters=len(page.get_text()),drawings=len(page.get_drawings()),images=len(page.get_images()),head=page.get_text()[:65],tail=page.get_text()[-80:]))
sheets(paths,out);(root/'artifacts/v9/page_audit.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf8')
(out/'full_text.txt').write_text('\n'.join(x.get_text() for x in p),encoding='utf8');print('Rendered',len(p),'pages',flush=True)
