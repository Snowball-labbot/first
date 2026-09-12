"""Native hidden Word export; stage messages identify any blocking step."""
from pathlib import Path
import json
import fitz
import win32com.client

root=Path(__file__).resolve().parents[1]
out=root/'.qa/v8/render_final';out.mkdir(parents=True,exist_ok=True)
print('Starting Word',flush=True)
app=win32com.client.DispatchEx('Word.Application')
app.Visible=False;app.DisplayAlerts=0;app.AutomationSecurity=3
doc=None
try:
    print('Opening manuscript',flush=True)
    doc=app.Documents.Open(str(root/'reports/完整论文_V8.docx'),ConfirmConversions=False,
        ReadOnly=True,AddToRecentFiles=False,OpenAndRepair=False,NoEncodingDialog=True)
    print('Repaginating',flush=True);doc.Repaginate()
    pages=doc.ComputeStatistics(2)
    print('Exporting '+str(pages)+' pages',flush=True)
    doc.ExportAsFixedFormat(str(root/'reports/完整论文_V8.pdf'),17)
    print('PDF exported',flush=True)
finally:
    if doc is not None:doc.Close(False)
    app.Quit()
pdf=fitz.open(root/'reports/完整论文_V8.pdf')
for i,p in enumerate(pdf):
    p.get_pixmap(matrix=fitz.Matrix(110/72,110/72)).save(out/f'page-{i+1}.png')
(out/'render_audit.json').write_text(json.dumps(dict(backend='Microsoft Word native PDF, PyMuPDF rasterization',pages=len(pdf))),encoding='utf-8')
print('Rendered '+str(len(pdf))+' pages',flush=True)
