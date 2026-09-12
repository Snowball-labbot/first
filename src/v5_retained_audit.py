"""Rerun retained Q1, Q2 and Q4-ahead decisions from raw inputs."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
from src.q12 import forecasts,backtest,optimize_day,dump_json
from src.q34_data import read_extended
from src.v3_model import run,Policy,risk_buffers

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args();out=Path('artifacts/v5')
    data,_=read_extended(a.data_root);pred,_=forecasts(data,'ridge',(1.,1.))
    L,V,p=[np.roll(data[k],1) for k in ['q1_load','q1_pv','price']]
    _,m=optimize_day(L,V,p,6000,(6000,'equal'));assert abs(m['cost']-35126.84858928963)<1e-7
    daily,_,state=backtest(data,pred,31,365,9902.811287870369,.7,'q2_reproduced',retain=False)
    old=pd.read_csv('artifacts/q12/ridge_q0.7_intervals.csv.gz')
    old_cost=(old.price*(old.plan_kwh+5*old.emergency_kwh)).groupby(old.date).sum().to_numpy()
    diff2=float(abs(daily.total_cost_yuan.to_numpy()-old_cost).max());assert diff2<1e-6
    ll=np.repeat(pred['load'][:,None,:],4,axis=1);pv=np.repeat(pred['pv'][:,None,:],4,axis=1);rr=risk_buffers(data,ll,pv,.7)
    r=run(data,ll,pv,rr,Policy(),start=31,stop=365,initial=9902.811287870369,name='q4_ahead_reproduced',prices=np.load('artifacts/q34/price_forecasts.npz')['ridge'],retain=False)
    old4=pd.read_csv('artifacts/v3/q4_2_ridge_daily.csv');diff4=float(abs(r[0].total_cost_yuan.to_numpy()-old4.total_cost_yuan.to_numpy()).max());assert diff4<1e-6
    result=dict(status='PASS',q1_milp_cost=m['cost'],q2_cost=float(daily.total_cost_yuan.sum()),q2_max_daily_difference=diff2,
        q4_ahead_cost=r[3]['total_cost_yuan'],q4_max_daily_difference=diff4,recomputed_days_per_stochastic_policy=334)
    dump_json(out/'retained_reproduction.json',result);print(result)
if __name__=='__main__':main()
