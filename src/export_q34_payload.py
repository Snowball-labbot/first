"""Create exact template payloads from the three validation-selected strategies."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from src.q12 import interval_label,dump_json
from src.deliver_q12 import blocks,emergency_runs


def main():
    out=Path('artifacts/q34');q3=json.loads((out/'q3_selection.json').read_text());q4=json.loads((out/'q4_selection.json').read_text())
    chosen={'3':f'q3_m{q3["mask"]}','4-2':f'q4_2_{q4["selected"]["2"]}','4-3':f'q4_3_{q4["selected"]["3"]}'}
    payload={}
    for key,name in chosen.items():
        f=pd.read_csv(out/f'{name}_intervals.csv.gz');daily=pd.read_csv(out/f'{name}_daily.csv').set_index('date')
        rows=[];adjusted=[];storage=[];emergency=[];ledgers=[]
        for date,g in f.groupby('date',sort=False):
            d=daily.loc[date];original=g.original_plan_kwh.to_list();effective=g.plan_kwh.to_list()
            rows.append([date,*original,float(sum(original)),float(d.total_cost_yuan if key=='4-2' else d.original_cost_yuan)])
            adjusted.append([date,*effective,float(sum(effective)),float(d.total_cost_yuan)])
            for i,b in enumerate(blocks(g)):
                storage.append([date if i==0 else None,*b,'00:00' if i==0 else '24:00' if i==1 else None,
                    float(g.soc_start_kwh.iloc[0]) if i==0 else float(g.soc_end_kwh.iloc[-1]) if i==1 else None])
            for i,r in enumerate(emergency_runs(g) or [['无',0.]]):emergency.append([date if i==0 else None,*r])
            ledgers.append([date,*[float(d[c]) for c in ['original_cost_yuan','increase_cost_yuan','decrease_cost_yuan','emergency_cost_yuan','total_cost_yuan']]])
        vp=out/f'{name}_versions.csv.gz';version_rows=[]
        if vp.exists():
            v=pd.read_csv(vp)
            for (date,version),g in v.groupby(['date','version'],sort=True):
                values=[None]*144
                for r in g.itertuples():values[int(r.slot)]=float(r.new_kwh)
                version_rows.append([date,f'{int(version)*6:02d}:00',*values])
        payload[key]={'strategy':name,'headers':['日期',*[interval_label(i) for i in range(144)],'全天购电量','全天购电费'],
            'plan':rows,'adjusted':adjusted,'storage':storage,'emergency':emergency,'versions':version_rows,'ledger':ledgers}
    dump_json(out/'xlsx_payload.json',payload);dump_json(out/'export_selection.json',chosen)
    print(chosen)


if __name__=='__main__':main()
