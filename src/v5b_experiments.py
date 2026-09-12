"""Screenshot-inspired tests: exact deterministic DP and causal Q2 recourse."""
from pathlib import Path
import argparse,time,json,hashlib
import numpy as np
import pandas as pd
from src.q12 import forecasts,optimize_day,reserve,execute_day,summarize_day,dump_json,audit_trace,B
from src.q34_data import read_extended
from src.v5b_value import deterministic,execute_value

OUT=Path('artifacts/v5b')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    design=dict(candidates=['greedy','value_zero','value_night'],scenario_days=28,risk_quantile=.7,
        terminal_rates={'value_zero':0,'value_night':'first-slot fixed price / charging efficiency'},
        validation=[21,31],evaluation=[31,365],selection='January realized fee; greedy wins ties',
        scenario='Paired historical load and PV residuals from completed days; nonnegative reconstructed levels',
        note='Mean historical perfect-information path values approximate continuation cost; causal action is not exact stochastic DP')
    dump_json(OUT/'design_before_evaluation.json',design)
    data,_=read_extended(a.data_root);pred,_=forecasts(data,'ridge',(1.,1.))
    L,V,p=[np.roll(data[k],1) for k in ['q1_load','q1_pv','price']]
    f,vals=deterministic(L,V,p);f.to_csv(OUT/'q1_dp_intervals.csv',index=False,float_format='%.17g')
    _,m=optimize_day(L,V,p,6000,(6000,'equal'));assert abs(m['cost']-p@f.plan_kwh)<1e-6
    checks=[]
    for s in [1200.,2400.,3600.,4800.,6000.,7200.,8400.,9600.,10800.]:
        _,ref=optimize_day(L,V,p,s,(6000,'equal'))
        val=float(vals[0].at(s));assert abs(val-ref['cost'])<1e-5
        checks.append(dict(initial_soc=s,dp_cost=val,milp_cost=ref['cost']))
    pd.DataFrame(checks).to_csv(OUT/'q1_state_value_check.csv',index=False)
    pd.DataFrame({'soc_kwh':vals[0].x,'future_cost_yuan':vals[0].y}).to_csv(OUT/'q1_initial_value.csv',index=False)
    print('Q1 continuous DP',float(p@f.plan_kwh),len(vals[0].x),'breakpoints',flush=True)
    def calc(name,start,stop,retain):
        s=6244.256891388887 if start==21 else 9902.811287870369;days=[];frames=[];tick=time.perf_counter()
        for day in range(start,stop):
            r=reserve(data,pred,day,.7);nominal,_=optimize_day(pred['load'][day]+r,pred['pv'][day],data['price'],s)
            plan=nominal.plan_kwh.to_numpy()
            if name=='greedy':f=execute_day(plan,data['load'][day],data['pv'][day],s,data['price'])
            else:
                left=max(7,day-28);l=np.maximum(0,pred['load'][day]+data['load'][left:day]-pred['load'][left:day]);v=np.maximum(0,pred['pv'][day]+data['pv'][left:day]-pred['pv'][left:day])
                paths=l-v-plan
                rate=0. if name=='value_zero' else float(data['price'][0]/B.eta_c)
                f=execute_value(plan,data['load'][day],data['pv'][day],s,data['price'],paths,rate)
            s=float(f.soc_end_kwh.iloc[-1]);days.append(summarize_day(f,data['dates'][day],name,0))
            if retain:f.insert(0,'date',str(data['dates'][day].date()));f.insert(1,'slot',range(144));frames.append(f)
            if retain and data['dates'][day].day==1:print(name,str(data['dates'][day].date()),flush=True)
        daily=pd.DataFrame(days);summary=dict(candidate=name,cost=float(daily.total_cost_yuan.sum()),emergency_kwh=float(daily.emergency_kwh.sum()),final_soc=s,seconds=time.perf_counter()-tick)
        if retain:
            trace=pd.concat(frames,ignore_index=True);summary['physical']=audit_trace(trace,initial=9902.811287870369)
            daily.to_csv(OUT/f'q2_{name}_daily.csv',index=False,float_format='%.17g');trace.to_csv(OUT/f'q2_{name}_intervals.csv.gz',index=False,float_format='%.17g')
        return summary
    validation=[calc(name,21,31,False) for name in design['candidates']];best=min(validation,key=lambda r:(r['cost'],r['candidate']!='greedy'))['candidate']
    dump_json(OUT/'validation.json',validation);dump_json(OUT/'selection.json',{'candidate':best});print('January',validation,best,flush=True)
    results=[calc(name,31,365,True) for name in design['candidates']];dump_json(OUT/'summary.json',results);print(results,flush=True)
    dump_json(OUT/'source_manifest.json',{str(f):hashlib.sha256(f.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for f in [Path(__file__),Path('src/v5b_value.py')]})
if __name__=='__main__':main()
