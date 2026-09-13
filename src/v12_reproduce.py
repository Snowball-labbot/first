"""Recompute the manuscript's frozen selected policies from original attachments.

Use --days 1 for a bounded replay; omit it for all 334 evaluation dates.
Monthly policy choices are frozen intermediate results, not refitted here.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
from src.q12 import forecasts, reserve, optimize_day, audit_trace
from src.q34_data import read_extended
from src.v3_model import solve, risk_buffers
from src.v5_model import adaptive_load
from src.v5b_value import execute_value
from src.v7_price import reconstruct
from src.v7_dispatch import execute_prefix
from src.v12_results import ROOT, SOURCES, EXPECTED


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data-root',type=Path,required=True)
    ap.add_argument('--days',type=int,default=334)
    ap.add_argument('--output',type=Path,default=ROOT/'artifacts/v12/recomputed')
    args=ap.parse_args()
    assert 1<=args.days<=334
    args.output.mkdir(parents=True,exist_ok=True)
    data,_=read_extended(args.data_root)
    pred,_=forecasts(data,'ridge',(1.,1.))
    prices,_=reconstruct(data)
    base=np.repeat(pred['load'][:,None,:],4,axis=1)
    loads={'baseline':base,'adaptive':adaptive_load(data,pred['load'])[0]}
    selected=pd.read_csv(ROOT/'artifacts/v5/online_selection.csv')
    q1,meta=solve(data['q1_load'],data['q1_pv'],data['price'],6000,equal=True)
    assert abs(q1.plan_kwh@data['price']-EXPECTED['1'])<1e-6
    q1.to_csv(args.output/'q1.csv',index=False)
    report={'1':{'cost_yuan':float(q1.plan_kwh@data['price']),'physical':audit_trace(q1,initial=6000)}}
    for key in ['2','3','4-2','4-3']:
        rolling=key in ['3','4-3']
        pv=data['pv_issued'] if rolling else np.repeat(pred['pv'][:,None,:],4,axis=1)
        buffers={k:risk_buffers(data,ll,pv,.5 if rolling else .7) for k,ll in loads.items()} if key!='2' else {}
        mode=3 if key=='3' else 4
        choices={int(r.month):r.candidate for r in selected[(selected['mode']==mode)&selected.selected].itertuples()}
        state=9902.811287870369
        frames=[]
        for day in range(31,31+args.days):
            date=str(data['dates'][day].date())
            if key=='2':
                rr=reserve(data,pred,day,.7)
                nominal,_=optimize_day(pred['load'][day]+rr,pred['pv'][day],data['price'],state)
                original=nominal.plan_kwh.to_numpy().copy()
                left=max(7,day-28)
                ll=np.maximum(0,pred['load'][day]+data['load'][left:day]-pred['load'][left:day])
                vv=np.maximum(0,pred['pv'][day]+data['pv'][left:day]-pred['pv'][left:day])
                f=execute_value(original,data['load'][day],data['pv'][day],state,data['price'],ll-vv-original,0.)
                actual=data['price']
            else:
                name=choices.get(int(data['dates'][day].month),'baseline') if rolling else 'baseline'
                ll=loads[name];rr=buffers[name]
                pp=None if key=='3' else prices['ridge' if key=='4-2' else 'seasonal']
                p0=data['price'] if pp is None else pp[day,0,:144]
                actual=data['price'] if pp is None else data['actual_price'][day]
                nominal,_=solve(ll[day,0]+rr[day,0],pv[day,0],p0,state)
                original=nominal.plan_kwh.to_numpy().copy();plan=original.copy();parts=[]
                for ver in (range(4) if rolling else [0]):
                    first=ver*36;steps=36 if rolling else 144
                    p=data['price'][first:] if pp is None else pp[day,ver,:144-first]
                    if ver:
                        nominal,_=solve(ll[day,ver,first:]+rr[day,ver,first:],pv[day,ver,first:],
                                        p,state,old=original[first:])
                        plan[first:]=np.maximum(nominal.plan_kwh,0)
                    left=max(7,day-28)
                    L=np.maximum(0,ll[day,ver,first:]+data['load'][left:day,first:]-ll[left:day,ver,first:])
                    V=np.maximum(0,pv[day,ver,first:]+data['pv'][left:day,first:]-pv[left:day,ver,first:])
                    part=execute_prefix(plan[first:],data['load'][day,first:],data['pv'][day,first:],
                        state,actual[first:],p,L-V-plan[first:],steps,rolling)
                    state=float(part.soc_end_kwh.iloc[-1]);parts.append(part)
                f=pd.concat(parts,ignore_index=True)
            state=float(f.soc_end_kwh.iloc[-1])
            f.insert(0,'date',date);f.insert(1,'slot',range(144))
            f['original_plan_kwh']=original
            final=f.plan_kwh.to_numpy()
            f['total_cost_yuan']=actual*(np.minimum(original,final)+.5*np.maximum(original-final,0)+
                                        1.5*np.maximum(final-original,0)+5*f.emergency_kwh.to_numpy())
            frames.append(f)
            print(key,date,flush=True)
        result=pd.concat(frames,ignore_index=True)
        reference=pd.read_csv(ROOT/SOURCES[key]).iloc[:len(result)]
        error={}
        for column in ['plan_kwh','charge_kwh','discharge_kwh','emergency_kwh','soc_start_kwh','soc_end_kwh']:
            error[column]=float(np.max(np.abs(result[column].to_numpy()-reference[column].to_numpy())))
            assert error[column]<1e-5,(key,column,error[column])
        result.to_csv(args.output/f'result{key}_intervals.csv.gz',index=False,float_format='%.17g')
        report[key]={'days':args.days,'cost_yuan':float(result.total_cost_yuan.sum()),
                     'max_absolute_difference':error,'physical':audit_trace(result,initial=9902.811287870369)}
        if args.days==334:
            assert abs(result.total_cost_yuan.sum()-EXPECTED[key])<1e-4
    report['status']='PASS'
    (args.output/'replay_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
