"""Q1 template-start sampling with explicit periodic midnight closure."""
from pathlib import Path
from dataclasses import replace
import argparse
import numpy as np
import pandas as pd
from src.q12 import read_inputs,optimize_day,B,dump_json,interval_label,audit_trace
from src.v3_model import solve

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args()
    data,_=read_inputs(a.data_root);out=Path('artifacts/v3');out.mkdir(parents=True,exist_ok=True)
    L,V,p=[np.roll(data[k],1) for k in ['q1_load','q1_pv','price']]
    f,meta=solve(L,V,p,6000,equal=True);_,milp=optimize_day(L,V,p,6000,(6000,'equal'))
    assert abs(meta['objective']-milp['cost'])<1e-6
    f.insert(0,'slot',range(144));f.insert(1,'interval',[interval_label(i) for i in range(144)])
    f.to_csv(out/'q1_intervals.csv',index=False,float_format='%.17g')
    sensitivity=[]
    for eta in [.8,.85,.9,np.sqrt(.9),1.]:
        b=replace(B,eta_c=eta,eta_d=eta);ff,mm=optimize_day(L,V,p,6000,(6000,'equal'),battery=b)
        audit_trace(ff,battery=b,initial=6000)
        sensitivity.append({'single_efficiency':eta,'roundtrip_efficiency':eta*eta,'cost':mm['cost']})
    pd.DataFrame(sensitivity).to_csv(out/'q1_efficiency.csv',index=False)
    dump_json(out/'q1_summary.json',{'cost':meta['objective'],'no_storage_cost':float(p@np.maximum(L-V,0)),
        'plan_kwh':float(f.plan_kwh.sum()),'charge_kwh':float(f.charge_kwh.sum()),'discharge_kwh':float(f.discharge_kwh.sum()),
        'milp':milp,'lp':meta,'specified':{interval_label(i):float(f.plan_kwh.iloc[i]) for i in [60,72,84,96,108,120]},
        'alignment':'Template start timestamps; Q1 periodic 24:00 sample fills 00:00 and all signals are jointly rotated; solve again with actual 00:00=24:00 SOC=6000.',
        'historical_series':'Q2-Q4 retained interval-average/right-end convention; no same-day final sample copied into their midnight histories.'})
    print('Q1',meta['objective'],milp['cost'])

if __name__=='__main__':main()
