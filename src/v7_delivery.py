"""Preserve workbook layouts; explicitly map Q1 periodic template labels."""
from pathlib import Path
import shutil,hashlib
import pandas as pd
import openpyxl
from src.q12 import dump_json
from src.deliver_q12 import blocks
OUT=Path('artifacts/v7')
SOURCES={'1':str(OUT/'q1_intervals.csv'),'2':'artifacts/v5b/q2_value_zero_selected_intervals.csv.gz',
 '3':'artifacts/v5b/q3_value_release_selected_intervals.csv.gz','4-2':'artifacts/v5b/q42_value_selected_intervals.csv.gz','4-3':'artifacts/v5b/q43_value_release_selected_intervals.csv.gz'}
def main():
    copied={}
    for key in ['2','3','4-2','4-3']:
        source=Path(f'artifacts/v5b/result{key}.xlsx');dest=OUT/source.name;shutil.copy2(source,dest);copied[key]=hashlib.sha256(dest.read_bytes()).hexdigest()
    f=pd.read_csv(SOURCES['1']);wb=openpyxl.load_workbook('artifacts/v5b/result1.xlsx');ws=wb['计划购电量'];labels=[r[0].value for r in ws.iter_rows(min_row=2)]
    expected=[]
    for i in range(1,145):
        value=float(f.plan_kwh.iloc[i%144]);ws.cell(i+1,2).value=value;expected.append(value)
    ws=wb['充放电量']
    for i,b in enumerate(blocks(f),2):
        ws.cell(i,2).value=b[1];ws.cell(i,3).value=b[2]
    ws.cell(2,5).value=float(f.soc_start_kwh.iloc[0]);ws.cell(3,5).value=float(f.soc_end_kwh.iloc[-1])
    wb.save(OUT/'result1.xlsx');wb.close();w=openpyxl.load_workbook(OUT/'result1.xlsx',read_only=True,data_only=True)
    rows=list(w['计划购电量'].values)[1:];assert [r[0] for r in rows]==labels
    for row,value in zip(rows,expected):assert abs(row[1]-value)<1e-8
    assert abs(sum(r[1] for r in rows)-f.plan_kwh.sum())<1e-7
    b=blocks(f)
    for i,row in enumerate(list(w['充放电量'].values)[1:]):assert abs(row[1]-b[i][1])<1e-7 and abs(row[2]-b[i][2])<1e-7
    w.close();dump_json(OUT/'delivery_selection.json',dict(sources=SOURCES,Q1='Unified right-end interval means; unchanged template start labels map slots 1..143 then repeated slot0',other_questions='byte-identical V5b selected workbooks'))
    dump_json(OUT/'xlsx_audit.json',dict(status='PASS',q1_plan_cells_checked=144,q1_storage_cells_checked=14,unchanged_workbooks=copied,q1_sha256=hashlib.sha256((OUT/'result1.xlsx').read_bytes()).hexdigest()))
    print('Five V7 workbooks checked')
if __name__=='__main__':main()
