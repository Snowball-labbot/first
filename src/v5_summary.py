from pathlib import Path
import json
import numpy as np
import pandas as pd
from src.q12 import dump_json

def main():
    out=Path('artifacts/v5');rows=[];months=[];rng=np.random.default_rng(20260912)
    for mode in [3,4]:
        b=pd.read_csv(out/f'q{mode}_baseline_daily.csv');c=pd.read_csv(out/f'q{mode}_online_daily.csv')
        diff=b.total_cost_yuan.to_numpy()-c.total_cost_yuan.to_numpy()
        row=dict(mode=mode,baseline_cost=float(b.total_cost_yuan.sum()),v5_cost=float(c.total_cost_yuan.sum()),saving=float(diff.sum()),
            saving_percent=float(diff.sum()/b.total_cost_yuan.sum()*100),baseline_emergency=float(b.emergency_kwh.sum()),
            v5_emergency=float(c.emergency_kwh.sum()),initial_soc_difference=float(c.soc_start_kwh.iloc[0]-b.soc_start_kwh.iloc[0]),
            final_soc_difference=float(c.soc_end_kwh.iloc[-1]-b.soc_end_kwh.iloc[-1]),bootstrap=[])
        for block in [7,14,28]:
            start=rng.integers(0,334,(2000,int(np.ceil(334/block))));ix=((start[:,:,None]+np.arange(block))%334).reshape(2000,-1)[:,:334]
            lo,hi=np.quantile(diff[ix].sum(axis=1),[.025,.975]);row['bootstrap'].append(dict(block_days=block,low=float(lo),high=float(hi)))
        rows.append(row)
        for month in range(2,13):
            mask=pd.to_datetime(b.date).dt.month==month
            months.append(dict(mode=mode,month=month,baseline=float(b.loc[mask,'total_cost_yuan'].sum()),online=float(c.loc[mask,'total_cost_yuan'].sum()),saving=float(diff[mask].sum())))
    dump_json(out/'improvement.json',rows);pd.DataFrame(months).to_csv(out/'monthly_comparison.csv',index=False)
    from src.q12 import B
    pmax=json.loads((out/'verification.json').read_text(encoding='utf-8'))['input_audit']['checks']['actual_price']['max']
    selections=pd.read_csv(out/'online_selection.csv');sensitivity=[]
    for (mode,month),g in selections.groupby(['mode','month']):
        a=g[g.selected].iloc[0];b=g[~g.selected].iloc[0]
        gap=float(b.cost-a.cost);value=float(5*pmax/B.eta_c*abs(b.final_soc-a.final_soc))
        sensitivity.append(dict(mode=int(mode),month=int(month),cost_gap=gap,max_inventory_adjustment=value,unchanged=gap>value))
    pd.DataFrame(sensitivity).to_csv(out/'selection_inventory_sensitivity.csv',index=False)
    print(json.dumps(rows,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
