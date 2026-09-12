"""State-value control in the remaining three cases, with causal prices."""
from pathlib import Path
import argparse,json,time
import numpy as np
import pandas as pd
from src.q12 import B,forecasts,audit_trace,execute_day,dump_json
from src.q34_data import read_extended
from src.v3_model import solve,risk_buffers
from src.v5_model import adaptive_load
from src.v5b_value import recourse_values

OUT=Path('artifacts/v5b')
def execute_prefix(plan,load,pv,initial,actual_price,forecast_price,paths,steps,release_aware=False):
    """Future values use forecast prices; only executed slots read real prices."""
    continuation_price=np.array(forecast_price,copy=True)
    # Beyond the next release, additional ordinary contracts cost 1.5p rather
    # than 5p. This is a value-function approximation, not a new billing rule.
    if release_aware:continuation_price[steps:]*=.3
    values=[recourse_values(path,continuation_price,0.) for path in paths];s=float(initial);rows=[]
    for t in range(steps):
        g,l,v,p=plan[t],load[t],pv[t],actual_price[t];net=float(l-v-g);c=d=e=w=0.
        if net<=0:c=min(-net,B.limit,(B.maximum-s)/B.eta_c);w=-net-c;end=s+B.eta_c*c
        else:
            lo=max(B.minimum,s-min(net,B.limit)/B.eta_d);choices=np.unique(np.r_[lo,s,*[f[t+1].x[(f[t+1].x>lo)&(f[t+1].x<s)] for f in values]])
            costs=5*p*(net-B.eta_d*(s-choices))+np.mean([f[t+1].at(choices) for f in values],axis=0)
            end=float(choices[np.argmin(costs)]);d=B.eta_d*(s-end);e=max(0,net-d)
        rows.append([g,l,v,c,d,e,w,s,end,p]);s=end
    f=pd.DataFrame(rows,columns=['plan_kwh','load_kwh','pv_kwh','charge_kwh','discharge_kwh','emergency_kwh','spill_kwh','soc_start_kwh','soc_end_kwh','price'])
    audit_trace(f,initial=initial);return f


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);ap.add_argument('--case',choices=['q3','q42','q43'],required=True);ap.add_argument('--extra-only',action='store_true');a=ap.parse_args()
    case=a.case;rolling=case!='q42';q=.5 if rolling else .7
    controls=['greedy','value','value_release'] if rolling else ['greedy','value']
    dump_json(OUT/f'{case}_design.json',dict(candidates=controls,selection='January cost; greedy wins ties',
        quantile=q,terminal=6000,scenario_days=28,terminal_value_rate=0.,
        load_selector='Retain earlier V5 causal monthly load selections as a shared forecast input',
        price_information='Only the executed slot sees actual prices; future value uses current-release price forecast',
        release_extension='Added after January frozen-contract value performed poorly; assumes future shortage can enter a 1.5p adjusted contract after next issue. Actual bills unchanged.'))
    data,_=read_extended(a.data_root);pred,_=forecasts(data,'ridge',(1.,1.));base=np.repeat(pred['load'][:,None,:],4,axis=1)
    loads={'baseline':base,'adaptive':adaptive_load(data,pred['load'])[0]}
    pv=data['pv_issued'] if rolling else np.repeat(pred['pv'][:,None,:],4,axis=1)
    rr={k:risk_buffers(data,ll,pv,q) for k,ll in loads.items()}
    pp=None if case=='q3' else np.load('artifacts/q34/price_forecasts.npz')['ridge' if case=='q42' else 'seasonal']
    selections=pd.read_csv('artifacts/v5/online_selection.csv');mode=3 if case=='q3' else 4
    choices={int(r.month):r.candidate for r in selections[(selections['mode']==mode)&selections.selected].itertuples()}
    def run(control,start,stop,retain):
        state=6244.256891388887 if start==21 else 9902.811287870369;frames=[];daily=[];versions=[];tick=time.perf_counter()
        for day in range(start,stop):
            date=str(data['dates'][day].date());month=int(data['dates'][day].month);name=choices.get(month,'baseline') if rolling else 'baseline'
            ll=loads[name];buffer=rr[name];p0=data['price'] if pp is None else pp[day,0,:144];actual=data['price'] if pp is None else data['actual_price'][day]
            nominal,_=solve(ll[day,0]+buffer[day,0],pv[day,0],p0,state);original=nominal.plan_kwh.to_numpy().copy();plan=original.copy();blocks=[]
            for ver in (range(4) if rolling else [0]):
                first=ver*36;steps=36 if rolling else 144;p=data['price'][first:] if pp is None else pp[day,ver,:144-first]
                if ver:
                    old=plan[first:].copy();nominal,_=solve(ll[day,ver,first:]+buffer[day,ver,first:],pv[day,ver,first:],p,state,old=original[first:]);plan[first:]=np.maximum(nominal.plan_kwh,0)
                    if retain:
                        for j,t in enumerate(range(first,144)):versions.append([date,ver,first,t,float(old[j]),float(plan[t]),float(p[j]),float(ll[day,ver,t]),float(pv[day,ver,t]),float(buffer[day,ver,t]),state])
                if control=='greedy':f=execute_day(plan[first:first+steps],data['load'][day,first:first+steps],data['pv'][day,first:first+steps],state,actual[first:first+steps])
                else:
                    left=max(7,day-28)
                    L=np.maximum(0,ll[day,ver,first:]+data['load'][left:day,first:]-ll[left:day,ver,first:])
                    V=np.maximum(0,pv[day,ver,first:]+data['pv'][left:day,first:]-pv[left:day,ver,first:])
                    f=execute_prefix(plan[first:],data['load'][day,first:],data['pv'][day,first:],state,actual[first:],p,L-V-plan[first:],steps,control=='value_release')
                state=float(f.soc_end_kwh.iloc[-1]);blocks.append(f)
            f=pd.concat(blocks,ignore_index=True);f.insert(0,'date',date);f.insert(1,'slot',range(144));f['original_plan_kwh']=original
            f['increase_kwh']=np.maximum(plan-original,0);f['decrease_kwh']=np.maximum(original-plan,0)
            f['original_cost_yuan']=actual*original;f['increase_cost_yuan']=1.5*actual*f.increase_kwh;f['decrease_cost_yuan']=-.5*actual*f.decrease_kwh;f['emergency_cost_yuan']=5*actual*f.emergency_kwh
            f['total_cost_yuan']=f[['original_cost_yuan','increase_cost_yuan','decrease_cost_yuan','emergency_cost_yuan']].sum(axis=1)
            daily.append(dict(date=date,soc_start_kwh=float(f.soc_start_kwh.iloc[0]),soc_end_kwh=state,
                **{k:float(f[k].sum()) for k in ['total_cost_yuan','original_cost_yuan','increase_cost_yuan','decrease_cost_yuan','emergency_cost_yuan','plan_kwh','emergency_kwh','charge_kwh','discharge_kwh','spill_kwh']}))
            if retain:frames.append(f)
            if retain and data['dates'][day].day==1:print(case,control,date,flush=True)
        d=pd.DataFrame(daily);s=dict(case=case,control=control,cost=float(d.total_cost_yuan.sum()),final_soc=state,emergency_kwh=float(d.emergency_kwh.sum()),seconds=time.perf_counter()-tick)
        if retain:
            f=pd.concat(frames,ignore_index=True);s['physical']=audit_trace(f,initial=9902.811287870369);d.to_csv(OUT/f'{case}_{control}_daily.csv',index=False,float_format='%.17g');f.to_csv(OUT/f'{case}_{control}_intervals.csv.gz',index=False,float_format='%.17g')
            if versions:pd.DataFrame(versions,columns=['date','version','effective_slot','slot','old_kwh','new_kwh','forecast_price','forecast_load_kwh','forecast_pv_kwh','reserve_kwh','decision_soc_kwh']).to_csv(OUT/f'{case}_{control}_versions.csv.gz',index=False,float_format='%.17g')
        return s
    prior=json.loads((OUT/f'{case}_validation.json').read_text(encoding='utf-8'))['validation'] if a.extra_only else []
    selected_controls=['value_release'] if a.extra_only else controls
    val=prior+[run(c,21,31,False) for c in selected_controls];chosen=min(val,key=lambda x:(x['cost'],x['control']!='greedy'))['control']
    dump_json(OUT/f'{case}_validation.json',{'validation':val,'selected':chosen});print(case,'January',val,chosen,flush=True)
    prior=json.loads((OUT/f'{case}_summary.json').read_text(encoding='utf-8')) if a.extra_only else []
    results=prior+[run(c,31,365,True) for c in selected_controls];dump_json(OUT/f'{case}_summary.json',results);print(case,results,flush=True)
if __name__=='__main__':main()
