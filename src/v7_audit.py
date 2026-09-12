"""Unified time convention, independent value audit and operational flexibility."""
from pathlib import Path
from dataclasses import replace
import argparse,json,hashlib
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from src.q12 import B,read_inputs,optimize_day,audit_trace,dump_json,interval_label
from src.v3_model import solve
from src.v5b_value import deterministic,recourse_values
from src.v5_audit import independent_lp
OUT=Path('artifacts/v7')
def path_lp(net,p,s,terminal_rate):
    n=len(net);I=np.eye(n);Z=np.zeros((n,n));T=np.tril(np.ones((n,n)))
    # c,d,e,w plus terminal shortfall; fixed surplus/deficit sign rules.
    eq=np.hstack([-I,I,I,-I,np.zeros((n,1))]);soc=np.hstack([B.eta_c*T,-T/B.eta_d,Z,Z,np.zeros((n,1))])
    ub=np.vstack([soc,-soc,np.r_[-soc[-1,:-1],-1.]])
    rhs=np.r_[np.full(n,B.maximum-s),np.full(n,s-B.minimum),s-6000]
    bounds=[]
    for variable in range(4):
        for a in net:
            maximum=(min(-a,B.limit) if a<=0 else 0) if variable==0 else (min(a,B.limit) if a>0 else 0) if variable==1 else (max(a,0) if variable==2 else max(-a,0))
            bounds.append((0,maximum))
    bounds.append((0,None));c=np.r_[np.zeros(2*n),5*p,np.zeros(n),terminal_rate]
    r=linprog(c,A_eq=eq,b_eq=net,A_ub=ub,b_ub=rhs,bounds=bounds,method='highs');assert r.success
    return float(r.fun)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args();OUT.mkdir(exist_ok=True,parents=True)
    D,inputs=read_inputs(a.data_root);L,V,p=[D[k] for k in ['q1_load','q1_pv','price']]
    f,m=solve(L,V,p,6000,equal=True);dp,val=deterministic(L,V,p)
    _,milp=optimize_day(L,V,p,6000,(6000,'equal'));cert=independent_lp(L,V,p,6000,equal=True)
    assert max(abs(m['objective']-x) for x in [p@dp.plan_kwh,milp['cost'],cert['objective']])<1e-6
    f.insert(0,'slot',range(144));f.insert(1,'interval',[interval_label(i) for i in range(144)]);f.to_csv(OUT/'q1_intervals.csv',index=False,float_format='%.17g')
    dp.to_csv(OUT/'q1_dp_intervals.csv',index=False,float_format='%.17g')
    pd.DataFrame({'soc_kwh':val[0].x,'cost_yuan':val[0].y}).to_csv(OUT/'q1_value.csv',index=False)
    no=float(p@np.maximum(L-V,0));savings=no-m['objective'];states=[]
    for s in np.arange(1200,10801,600):
        _,r=optimize_day(L,V,p,float(s),(6000,'equal'))
        error=abs(float(val[0].at(s))-r['cost']);assert error<1e-5;states.append(dict(initial_soc=s,dp=float(val[0].at(s)),milp=r['cost'],error=error))
    pd.DataFrame(states).to_csv(OUT/'state_checks.csv',index=False)
    # Power remains 5000 kW. Increase usable capacity symmetrically around the
    # same 6000-kWh initial and terminal state, avoiding free initial energy.
    capacity=[]
    for width in [0.,2400.,4800.,7200.,9600.,12000.]:
        b=replace(B,minimum=6000-width/2,maximum=6000+width/2)
        _,r=optimize_day(L,V,p,6000,(6000,'equal'),battery=b)
        capacity.append(dict(usable_capacity_kwh=width,cost=r['cost'],flexibility_value=no-r['cost']))
    pd.DataFrame(capacity).to_csv(OUT/'capacity_value.csv',index=False)
    assert all(capacity[i]['cost']>=capacity[i+1]['cost']-1e-6 for i in range(len(capacity)-1))
    assert abs(capacity[0]['cost']-no)<1e-6
    slopes=np.diff([r['flexibility_value'] for r in capacity])/2400
    assert np.all(np.diff(slopes)<=1e-6)
    efficiency=[]
    for eta in [.8,.85,.9,np.sqrt(.9),1.]:
        _,r=optimize_day(L,V,p,6000,(6000,'equal'),battery=replace(B,eta_c=eta,eta_d=eta))
        efficiency.append(dict(single_efficiency=eta,roundtrip_efficiency=eta**2,cost=r['cost']))
    pd.DataFrame(efficiency).to_csv(OUT/'q1_efficiency.csv',index=False)
    rng=np.random.default_rng(20260912);path_checks=[]
    for i in range(48):
        n=[3,12,24,144][i%4];net=rng.uniform(-1300,1600,n);price=rng.uniform(.0076,1.7936,n);s=float(rng.uniform(1200,10800));rate=[0.,.5,2.][i%3]
        value=float(recourse_values(net,price,rate)[0].at(s));ref=path_lp(net,price,s,rate);error=abs(value-ref)
        assert error<1e-5,(i,error);path_checks.append(dict(case=i,n=n,initial=s,terminal_rate=rate,dp=value,lp=ref,error=error))
    pd.DataFrame(path_checks).to_csv(OUT/'path_value_checks.csv',index=False)
    summary=dict(cost=m['objective'],no_storage_cost=no,flexibility_value=savings,saving_percent=100*savings/no,plan_kwh=float(f.plan_kwh.sum()),
        initial_marginal_value=float((val[0].at(6000)-val[0].at(6001))),breakpoints=len(val[0].x),physical=audit_trace(f,initial=6000),lp_certificate=cert,
        interval_convention='All questions: input timestamp is right endpoint of a ten-minute mean interval; no cyclic input rotation. Q1 export alone maps its periodic actions to unchanged template start labels.',
        previous_v5_cost=35126.84858928963,time_convention_cost_change=m['objective']-35126.84858928963)
    dump_json(OUT/'q1_summary.json',summary)
    dump_json(OUT/'model_audit.json',dict(status='PASS',q1_state_tests=len(states),random_mixed_path_tests=len(path_checks),max_path_error=max(x['error'] for x in path_checks),
        raw_inputs=inputs['input_files'],capacity_concavity_pass=True,all_existing_stochastic_strategies='Unchanged V5b traces; reevaluated separately',sources={str(Path(__file__)):hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()}))
    print(summary);print('48 mixed-sign historical-path LP checks passed')
if __name__=='__main__':main()
