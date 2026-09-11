"""Causal receding-horizon dispatch with a versioned adjustment ledger."""
from pathlib import Path
import argparse
import hashlib
import json
import time
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix
from src.q12 import B, TOL, optimize_day, execute_day, audit_trace, forecasts, reserve, dump_json
from src.q34_data import read_extended


def revise_plan(load,pv,price,initial,old,refund=True):
    """Optimize only the unexecuted suffix; positive prices prohibit buy/sell loops."""
    n=len(price);size=8*n+1
    gi,ci,di,wi,si,zi,ui,vi=0,n,2*n,3*n,4*n,5*n+1,6*n+1,7*n+1
    objective=np.zeros(size);objective[ui:vi]=1.5*price
    objective[vi:]=(-.5 if refund else .5)*price
    lb=np.zeros(size);ub=np.full(size,np.inf)
    ub[ci:wi]=B.limit;lb[si:zi]=B.minimum;ub[si:zi]=B.maximum
    lb[si]=ub[si]=initial;lb[si+n]=6000
    ub[zi:ui]=1;ub[vi:]=np.maximum(old,0)
    integer=np.zeros(size);integer[zi:ui]=1
    a=lil_matrix((5*n,size));lo=np.zeros(5*n);hi=np.zeros(5*n)
    for t in range(n):
        a[t,gi+t],a[t,ci+t],a[t,di+t],a[t,wi+t]=1,-1,1,-1
        lo[t]=hi[t]=load[t]-pv[t]
        a[n+t,si+t+1],a[n+t,si+t],a[n+t,ci+t],a[n+t,di+t]=1,-1,-B.eta_c,1/B.eta_d
        a[2*n+t,ci+t],a[2*n+t,zi+t]=1,-B.limit;lo[2*n+t]=-np.inf
        a[3*n+t,di+t],a[3*n+t,zi+t]=1,B.limit;lo[3*n+t]=-np.inf;hi[3*n+t]=B.limit
        a[4*n+t,gi+t],a[4*n+t,ui+t],a[4*n+t,vi+t]=1,-1,1
        lo[4*n+t]=hi[4*n+t]=old[t]
    started=time.perf_counter()
    fit=milp(objective,integrality=integer,bounds=Bounds(lb,ub),
        constraints=LinearConstraint(a.tocsc(),lo,hi),options={'time_limit':30,'mip_rel_gap':1e-7})
    if not fit.success:raise RuntimeError(fit.message)
    x=fit.x
    assert not ((x[ui:vi]>TOL)&(x[vi:]>TOL)).any()
    f=pd.DataFrame({'plan_kwh':x[:n],'charge_kwh':x[ci:di],'discharge_kwh':x[di:wi],
        'spill_kwh':x[wi:si],'soc_start_kwh':x[si:si+n],'soc_end_kwh':x[si+1:zi],
        'load_kwh':load,'pv_kwh':pv,'emergency_kwh':np.zeros(n),'price':price})
    audit_trace(f,initial=initial)
    return f,{'seconds':time.perf_counter()-started,'gap':float(fit.mip_gap),'objective':float(fit.fun)}


def historical_buffers(data,pred,q):
    """Match publication version and target clock time; use completed prior days."""
    buffers=np.full((len(pred['load']),4,144),np.nan)
    for day in range(len(buffers)):
        for version in range(4):
            start=36*version;buffers[day,version,start:]=0
            if q==0 or day<7:continue
            left=max(1,day-28)
            errors=(data['load'][left:day]-data['pv'][left:day]-pred['load'][left:day]
                    +data['pv_issued'][left:day,version])
            for t in range(start,144):
                buffers[day,version,t]=max(0.,float(np.quantile(errors[:,max(start,t-3):min(144,t+4)],q)))
    return buffers


def backtest(data,pred,buffers,*,start,stop,initial,mask,name,price_forecasts=None,
             use_issued=True,refund=True,retain=True):
    state=float(initial);daily=[];frames=[];versions=[];solver_seconds=0.
    for day in range(start,stop):
        date=str(data['dates'][day].date());s0=state
        prices=data['price'] if price_forecasts is None else data['actual_price'][day]
        p0=data['price'] if price_forecasts is None else price_forecasts[day,0,:144]
        pv=data['pv_issued'][day,0] if use_issued else pred['pv'][day]
        buffer=buffers[day,0] if use_issued else reserve(data,pred,day,.7)
        solution,meta=optimize_day(pred['load'][day]+buffer,pv,p0,state)
        solver_seconds+=meta['seconds'];plan=np.maximum(0,solution.plan_kwh.to_numpy())
        original=plan.copy();up_total=np.zeros(144);down_total=np.zeros(144)
        day_frames=[]
        for version in range(4):
            t0=version*36;t1=t0+36
            if version and mask & (1<<(version-1)):
                if not use_issued:raise ValueError('Q4-2 cannot update plans')
                frozen=plan[:t0].copy();old=plan[t0:].copy()
                price=data['price'][t0:] if price_forecasts is None else price_forecasts[day,version,:144-t0]
                pv=data['pv_issued'][day,version,t0:];buffer=buffers[day,version,t0:]
                sol,meta=revise_plan(pred['load'][day,t0:]+buffer,pv,price,state,old,refund)
                solver_seconds+=meta['seconds'];new=np.maximum(0,sol.plan_kwh.to_numpy())
                delta=new-old;up=np.maximum(delta,0);down=np.maximum(-delta,0)
                up_total[t0:]+=up;down_total[t0:]+=down;plan[t0:]=new
                np.testing.assert_array_equal(frozen,plan[:t0])
                if retain:
                    for j,t in enumerate(range(t0,144)):
                        versions.append((date,version,t0,t,old[j],new[j],up[j],down[j],price[j],
                            pred['load'][day,t],pv[j],buffer[j],state))
            block=execute_day(plan[t0:t1],data['load'][day,t0:t1],data['pv'][day,t0:t1],state,prices[t0:t1])
            state=float(block.soc_end_kwh.iloc[-1]);day_frames.append(block)
        f=pd.concat(day_frames,ignore_index=True)
        f.insert(0,'date',date);f.insert(1,'slot',np.arange(144))
        f['original_plan_kwh']=original;f['increase_kwh']=up_total;f['decrease_kwh']=down_total
        f['original_cost_yuan']=prices*original;f['increase_cost_yuan']=prices*1.5*up_total
        f['decrease_cost_yuan']=prices*(-.5 if refund else .5)*down_total
        f['emergency_cost_yuan']=prices*5*f.emergency_kwh
        f['total_cost_yuan']=f[['original_cost_yuan','increase_cost_yuan','decrease_cost_yuan','emergency_cost_yuan']].sum(axis=1)
        np.testing.assert_allclose(f.plan_kwh,original+up_total-down_total,atol=TOL,rtol=0)
        assert (f.total_cost_yuan>=-TOL).all()
        item={'date':date,'strategy':name,'soc_start_kwh':s0,'soc_end_kwh':state}
        for col in ['original_cost_yuan','increase_cost_yuan','decrease_cost_yuan','emergency_cost_yuan',
                    'total_cost_yuan','original_plan_kwh','plan_kwh','increase_kwh','decrease_kwh','emergency_kwh','spill_kwh']:
            item[col]=float(f[col].sum())
        item['emergency_intervals']=int((f.emergency_kwh>TOL).sum());daily.append(item)
        if retain:frames.append(f)
    trace=pd.concat(frames,ignore_index=True) if frames else None
    physical=audit_trace(trace,initial=initial) if trace is not None else None
    daily=pd.DataFrame(daily)
    ledger=pd.DataFrame(versions,columns=['date','version','effective_slot','slot','old_kwh','new_kwh',
        'increase_kwh','decrease_kwh','forecast_price','forecast_load_kwh','forecast_pv_kwh','reserve_kwh','decision_soc_kwh'])
    sums={c:float(daily[c].sum()) for c in daily if c.endswith('_yuan') or c in ['emergency_kwh','increase_kwh','decrease_kwh','spill_kwh']}
    summary={'strategy':name,'mask':mask,'refund':refund,'days':stop-start,'initial_soc':initial,'final_soc':state,
        'solver_seconds':solver_seconds,'physical':physical,**sums}
    return daily,trace,ledger,summary


def save_run(out,name,result):
    daily,trace,versions,summary=result
    daily.to_csv(out/f'{name}_daily.csv',index=False,float_format='%.17g')
    if trace is not None:trace.to_csv(out/f'{name}_intervals.csv.gz',index=False,float_format='%.17g')
    if len(versions):versions.to_csv(out/f'{name}_versions.csv.gz',index=False,float_format='%.17g')
    dump_json(out/f'{name}_summary.json',summary)
    print(f'{name}: cost={summary["total_cost_yuan"]:.2f}, emergency={summary["emergency_kwh"]:.2f}, solver={summary["solver_seconds"]:.1f}s',flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--data-root',required=True)
    p.add_argument('--out',type=Path,default=Path('artifacts/q34'));p.add_argument('--smoke',action='store_true')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    data,audit=read_extended(args.data_root,args.out/'input_audit.json')
    pred,_=forecasts(data,'ridge',(1.,1.))
    buffers={q:historical_buffers(data,pred,q) for q in [0.,.7,.9]}
    s_validation=6244.256891388887;s_evaluation=9902.811287870369
    validation=[]
    for q in buffers:
        for mask in range(8):
            result=backtest(data,pred,buffers[q],start=21,stop=31,initial=s_validation,
                mask=mask,name=f'q3_q{q}_m{mask}',retain=False)
            validation.append({**result[-1],'quantile':q})
    v=pd.DataFrame(validation);v.to_csv(args.out/'q3_validation.csv',index=False,float_format='%.17g')
    best=min(validation,key=lambda r:(r['total_cost_yuan'],r['quantile'],r['mask']))
    q=best['quantile'];selected_mask=best['mask'];stop=38 if args.smoke else 365
    selection={'quantile':q,'mask':selected_mask,'validation_days':'2025-01-22/2025-01-31',
        'selection':'minimum validation total cost, then smaller q and mask',
        'initial_evaluation_soc_kwh':s_evaluation,'refund':True}
    dump_json(args.out/'q3_selection.json',selection)
    for mask in range(8):
        name=f'q3_m{mask}'
        save_run(args.out,name,backtest(data,pred,buffers[q],start=31,stop=stop,initial=s_evaluation,mask=mask,name=name))
    no_refund=[]
    for mask in range(8):
        name=f'q3_no_refund_m{mask}'
        result=backtest(data,pred,buffers[q],start=31,stop=stop,initial=s_evaluation,mask=mask,name=name,refund=False,
            retain=(mask==selected_mask))
        save_run(args.out,name,result);no_refund.append(result[-1])
    dump_json(args.out/'q3_fee_sensitivity.json',no_refund)
    dump_json(args.out/'q3_run_manifest.json',{'stage':'smoke' if args.smoke else 'full','elapsed_seconds':time.perf_counter()-started,
        'selection':selection,'input_files':audit['input_files'],
        'source_sha256':{f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in ['src/q12.py','src/q34.py','src/q34_data.py']}})


if __name__=='__main__':main()
