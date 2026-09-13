"""Render representative ranges using native Excel, without saving the books."""
from pathlib import Path
import win32com.client
import fitz

root=Path(__file__).resolve().parents[1]
out=root/'.qa/v12/excel';out.mkdir(parents=True,exist_ok=True)
app=win32com.client.DispatchEx('Excel.Application')
app.Visible=False;app.DisplayAlerts=False;app.AutomationSecurity=3
try:
    for key,sheet,area in [('1','计划购电量','A1:B14'),('2','充放电量','A1:F13'),
                           ('2','紧急购电量','A1:C18'),('3','调整购电量','A1:H12'),
                           ('4-3','充放电量','A1:F13')]:
        book=app.Workbooks.Open(str(root/f'results/V12/附件5/result{key}.xlsx'),ReadOnly=True,UpdateLinks=0)
        try:
            ws=book.Worksheets(sheet)
            ws.PageSetup.PrintArea=area
            ws.PageSetup.Zoom=False;ws.PageSetup.FitToPagesWide=1;ws.PageSetup.FitToPagesTall=1
            path=out/f'result{key}_{sheet}.pdf'
            ws.ExportAsFixedFormat(0,str(path))
            pdf=fitz.open(path)
            assert len(pdf)==1
            pdf[0].get_pixmap(matrix=fitz.Matrix(1.7,1.7)).save(path.with_suffix('.png'))
            assert '###' not in pdf[0].get_text()
            print(path.name,flush=True)
        finally:book.Close(SaveChanges=False)
finally:app.Quit()
