"""Exact result-cell payloads; preserve populated V2 workbook layouts."""
from pathlib import Path
import json
import pandas as pd
from src.q12 import dump_json
from src.deliver_q12 import blocks,emergency_runs

def main():
    out=Path('artifacts/v3');sel=json.loads((out/'selection.json').read_text());payload={}
    chosen={'3':f'q3_m{sel["q3"]["mask"]}','4-2':f'q4_2_{sel["prices"]["2"]}','4-3':f'q4_3_{sel["prices"]["3"]}'}
    for key,name in chosen.items():
        f=pd.read_csv(out/f'{name}_intervals.csv.gz');plans=[];adjusted=[];storage=[];emergency=[];ledger=[];version_rows=[]
        for date,g in f.groupby('date',sort=False):
            plans.append([date,*g.original_plan_kwh.to_list(),float(g.original_plan_kwh.sum()),float(g.total_cost_yuan.sum() if key=='4-2' else g.original_cost_yuan.sum())])
            adjusted.append([date,*g.plan_kwh.to_list(),float(g.plan_kwh.sum()),float(g.total_cost_yuan.sum())])
            for i,b in enumerate(blocks(g)):
                storage.append([date if i==0 else None,*b,'00:00' if i==0 else '24:00' if i==1 else None,float(g.soc_start_kwh.iloc[0]) if i==0 else float(g.soc_end_kwh.iloc[-1]) if i==1 else None])
            for i,b in enumerate(emergency_runs(g) or [['无',0.]]):emergency.append([date if i==0 else None,*b])
            ledger.append([date,*[float(g[c].sum()) for c in ['original_cost_yuan','increase_cost_yuan','decrease_cost_yuan','emergency_cost_yuan','total_cost_yuan']]])
        vp=out/f'{name}_versions.csv.gz'
        if vp.exists():
            v=pd.read_csv(vp)
            for (date,ver),g in v.groupby(['date','version'],sort=True):
                values=[None]*144
                for r in g.itertuples():values[int(r.slot)]=float(r.new_kwh)
                version_rows.append([date,f'{int(ver)*6:02d}:00',*values])
        payload[key]={'plan':plans,'adjusted':adjusted,'storage':storage,'emergency':emergency,'ledger':ledger,'versions':version_rows}
    q1=pd.read_csv(out/'q1_intervals.csv');b=blocks(q1)
    # Official Q1 template is ordered 00:10,...,24:00. Its last slot is the
    # first slot of the repeated day. Keep every original template label.
    payload['1']={'plan':[[float(q1.plan_kwh.iloc[i%144])] for i in range(1,145)],
        'storage':[[*b[i][1:],float(q1.soc_start_kwh.iloc[0]) if i==0 else float(q1.soc_end_kwh.iloc[-1]) if i==1 else None] for i in range(6)]}
    dump_json(out/'xlsx_payload.json',payload);dump_json(out/'delivery_selection.json',{'1':'q1_intervals.csv','2':'../v2/result2.xlsx',**chosen})

if __name__=='__main__':main()
