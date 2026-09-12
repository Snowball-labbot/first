"""Write V5 data cells into V3 layouts and read every written cell back."""
from pathlib import Path
from datetime import datetime
import json,shutil,math,hashlib
from copy import copy
import pandas as pd
import openpyxl
from src.q12 import dump_json
from src.deliver_q12 import blocks,emergency_runs

OUT=Path('artifacts/v5b')
from src.v5b_analysis import SELECTED
SOURCES={'1':'artifacts/v3/q1_intervals.csv',**{k:str(OUT/f'{v}_selected_intervals.csv.gz') for k,v in SELECTED.items()}}

def main():
    audit=[]
    for key in ['1']:shutil.copy2(f'artifacts/v3/result{key}.xlsx',OUT/f'result{key}.xlsx')
    for key,label in SELECTED.items():
        f=pd.read_csv(SOURCES[key]);v=pd.read_csv(OUT/f'{label}_versions.csv.gz') if key in ['3','4-3'] else pd.DataFrame();payload={k:[] for k in (['计划购电量','调整购电量','充放电量','紧急购电量','费用分解','计划版本'] if key in ['3','4-3'] else ['计划购电量','充放电量','紧急购电量']+(['费用分解'] if key=='4-2' else []))}
        for date,g in f.groupby('date',sort=False):
            dt=datetime.strptime(date,'%Y-%m-%d')
            payload['计划购电量'].append([dt,*g.original_plan_kwh.tolist(),float(g.original_plan_kwh.sum()),float(g.original_cost_yuan.sum()) if key in ['3','4-3'] else float(g.total_cost_yuan.sum())])
            if '调整购电量' in payload:payload['调整购电量'].append([dt,*g.plan_kwh.tolist(),float(g.plan_kwh.sum()),float(g.total_cost_yuan.sum())])
            for i,b in enumerate(blocks(g)):
                payload['充放电量'].append([dt if i==0 else None,*b,'00:00' if i==0 else '24:00' if i==1 else None,float(g.soc_start_kwh.iloc[0]) if i==0 else float(g.soc_end_kwh.iloc[-1]) if i==1 else None])
            for i,b in enumerate(emergency_runs(g) or [['无',0.]]):payload['紧急购电量'].append([dt if i==0 else None,*b])
            if '费用分解' in payload:payload['费用分解'].append([dt,*[float(g[c].sum()) for c in ['original_cost_yuan','increase_cost_yuan','decrease_cost_yuan','emergency_cost_yuan','total_cost_yuan']]])
        for (date,ver),g in (v.groupby(['date','version'],sort=True) if len(v) else []):
            values=[None]*144
            for r in g.itertuples():values[int(r.slot)]=float(r.new_kwh)
            payload['计划版本'].append([datetime.strptime(date,'%Y-%m-%d'),f'{int(ver)*6:02d}:00',*values])
        wb=openpyxl.load_workbook(f'artifacts/v5/result{key}.xlsx');assert not any(c.data_type=='f' for ws in wb for row in ws for c in row),'Formula-bearing template needs recalculation'
        headers={ws.title:tuple(c.value for c in ws[1]) for ws in wb};sheets=wb.sheetnames
        for name,rows in payload.items():
            ws=wb[name];end=ws.max_row;columns=len(rows[0])
            for row in ws.iter_rows(min_row=2,max_row=max(end,len(rows)+1),max_col=columns):
                for cell in row:cell.value=None
            for i,row in enumerate(rows,2):
                for j,value in enumerate(row,1):
                    cell=ws.cell(i,j);cell.value=value
                    if i>end:cell._style=copy(ws.cell(2,j)._style)
        if '口径说明' in wb:wb['口径说明']['B2']='V5复核更新：过去28日配对残差价值控制；日前按固定合同，滚动按后续可调单成本估计库存价值；实际费用规则不变。'
        dest=OUT/f'result{key}.xlsx';wb.save(dest);wb.close()
        checked=openpyxl.load_workbook(dest,read_only=True,data_only=True);count=0
        assert checked.sheetnames==sheets
        for name in sheets:assert tuple(next(checked[name].values))==headers[name]
        for name,rows in payload.items():
            for actual,expected in zip(checked[name].iter_rows(min_row=2,max_row=len(rows)+1,max_col=len(rows[0]),values_only=True),rows):
                for a,e in zip(actual,expected):
                    count+=1
                    if isinstance(e,(int,float)):assert isinstance(a,(int,float)) and math.isclose(a,e,abs_tol=1e-7,rel_tol=1e-11),(name,a,e)
                    else:assert a==e,(name,a,e)
            for row in checked[name].iter_rows(min_row=len(rows)+2,values_only=True):assert all(v is None for v in row)
        checked.close();audit.append(dict(key=key,cells_compared=count,headers_preserved=True,formula_cells=0,sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
    dump_json(OUT/'delivery_selection.json',{'sources':SOURCES,'main':'January-selected historical-path value controllers; Q1 unchanged','copied_byte_identical':['1']})
    dump_json(OUT/'xlsx_audit.json',dict(status='PASS',updated=audit,copied={k:hashlib.sha256((OUT/f'result{k}.xlsx').read_bytes()).hexdigest() for k in ['1']}));print(audit)
if __name__=='__main__':main()
