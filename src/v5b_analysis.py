"""Recompute bills from raw inputs, audit revisions and quantify paired gains."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import pandas as pd
from src.q12 import audit_trace,dump_json
from src.q34_data import read_extended
from src.v5_audit import independent_lp
OUT=Path('artifacts/v5b')
SELECTED={'2':'q2_value_zero','3':'q3_value_release','4-2':'q42_value','4-3':'q43_value_release'}
def canonical(name):
    f=pd.read_csv(OUT/f'{name}_intervals.csv.gz')
    if 'original_plan_kwh' not in f:
        f['original_plan_kwh']=f.plan_kwh
        f['original_cost_yuan']=f.price*f.plan_kwh
        f['increase_cost_yuan']=0.;f['decrease_cost_yuan']=0.
        f['emergency_cost_yuan']=5*f.price*f.emergency_kwh
        f['total_cost_yuan']=f.original_cost_yuan+f.emergency_cost_yuan
    return f
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args()
    data,_=read_extended(a.data_root);audits=[];certs=[]
    names=[p.name.removesuffix('_intervals.csv.gz') for p in OUT.glob('*_intervals.csv.gz')]
    for name in sorted(names):
        if name.endswith('_selected'):continue
        f=canonical(name);assert len(f)==334*144
        assert not f[['date','slot']].duplicated().any()
        assert f.date.tolist()==np.repeat(data['dates'][31:].strftime('%Y-%m-%d'),144).tolist()
        np.testing.assert_array_equal(f.slot,np.tile(np.arange(144),334))
        for col,key in [('load_kwh','load'),('pv_kwh','pv')]:np.testing.assert_allclose(f[col],data[key][31:].reshape(-1),rtol=0,atol=1e-10)
        p=np.tile(data['price'],334) if name.startswith(('q2_','q3_')) else data['actual_price'][31:].reshape(-1)
        np.testing.assert_allclose(f.price,p,atol=1e-12,rtol=0)
        fee=p*(np.minimum(f.original_plan_kwh,f.plan_kwh)+.5*np.maximum(f.original_plan_kwh-f.plan_kwh,0)+1.5*np.maximum(f.plan_kwh-f.original_plan_kwh,0)+5*f.emergency_kwh)
        np.testing.assert_allclose(fee,f.total_cost_yuan,atol=1e-7,rtol=0)
        d=pd.read_csv(OUT/f'{name}_daily.csv');np.testing.assert_allclose(fee.groupby(f.date).sum(),d.total_cost_yuan,atol=1e-6,rtol=0)
        physical=audit_trace(f,initial=9902.811287870369)
        vp=OUT/f'{name}_versions.csv.gz'
        if vp.exists():
            v=pd.read_csv(vp)
            for date,g in f.groupby('date',sort=False):
                plan=g.original_plan_kwh.to_numpy().copy()
                for ver in [1,2,3]:
                    z=v[(v.date==date)&(v.version==ver)];slots=z.slot.to_numpy(int)
                    np.testing.assert_array_equal(slots,np.arange(ver*36,144))
                    np.testing.assert_allclose(plan[slots],z.old_kwh,atol=1e-8,rtol=0)
                    assert abs(z.decision_soc_kwh.iloc[0]-g.soc_start_kwh.iloc[ver*36])<1e-8
                    plan[slots]=z.new_kwh
                np.testing.assert_allclose(plan,g.plan_kwh,atol=1e-8,rtol=0)
            if name in SELECTED.values():
                for date in ['2025-03-20','2025-06-21','2025-09-23','2025-12-21']:
                    for ver in [1,2,3]:
                        z=v[(v.date==date)&(v.version==ver)];g=f[(f.date==date)&(f.slot>=ver*36)]
                        c=independent_lp((z.forecast_load_kwh+z.reserve_kwh).to_numpy(),z.forecast_pv_kwh.to_numpy(),z.forecast_price.to_numpy(),float(z.decision_soc_kwh.iloc[0]),old=g.original_plan_kwh.to_numpy())
                        # The recorded future plan is a nominal optimizer; subsequent
                        # execution and reoptimizations need not follow its SOC path.
                        delta=z.new_kwh.to_numpy()-g.original_plan_kwh.to_numpy()
                        recorded=float(z.forecast_price.to_numpy()@(1.5*np.maximum(delta,0)-.5*np.maximum(-delta,0)))
                        assert abs(recorded-c['objective'])<1e-5
                        c.update(case=name,date=date,version=ver,recorded_difference=abs(recorded-c['objective']));certs.append(c)
        audits.append(dict(name=name,cost=float(fee.sum()),intervals=len(f),physical=physical))
    gains=[];monthly=[];rng=np.random.default_rng(20260912)
    for key,name in SELECTED.items():
        base=canonical(name.split('_')[0]+'_greedy');f=canonical(name)
        assert abs(f.soc_end_kwh.iloc[-1]-base.soc_end_kwh.iloc[-1])<1e-7
        diff=(base.total_cost_yuan-f.total_cost_yuan).groupby(f.date).sum().to_numpy();boots=[]
        for block in [7,14,28]:
            idx=(rng.integers(0,len(diff),(2000,int(np.ceil(len(diff)/block))))[:,:,None]+np.arange(block))%len(diff)
            sums=diff[idx.reshape(2000,-1)[:,:len(diff)]].sum(axis=1)
            lo,hi=np.quantile(sums,[.025,.975]);boots.append(dict(block=block,low=float(lo),high=float(hi)))
        record=dict(question=key,selected=name,baseline_cost=float(base.total_cost_yuan.sum()),cost=float(f.total_cost_yuan.sum()),saving=float(diff.sum()),percent=float(diff.sum()/base.total_cost_yuan.sum()*100),bootstrap=boots,initial_soc=float(f.soc_start_kwh.iloc[0]),final_soc=float(f.soc_end_kwh.iloc[-1]))
        for label,frame in [('before',base),('after',f)]:
            record[label]={c:float(frame[c].sum()) for c in ['original_cost_yuan','increase_cost_yuan','decrease_cost_yuan','emergency_cost_yuan','emergency_kwh','spill_kwh']}
        gains.append(record)
        for month in range(2,13):
            mask=pd.to_datetime(f.date).dt.month==month
            monthly.append(dict(question=key,month=month,saving=float((base.total_cost_yuan-f.total_cost_yuan)[mask].sum())))
        f.to_csv(OUT/f'{name}_selected_intervals.csv.gz',index=False,float_format='%.17g')
    periodic=[]
    for key in ['load','pv']:
        x=data[key]
        for lag in [1,7,14,28]:periodic.append(dict(series=key,lag_days=lag,slot_correlation=float(np.corrcoef(x[lag:].ravel(),x[:-lag].ravel())[0,1]),daily_energy_correlation=float(np.corrcoef(x[lag:].sum(1),x[:-lag].sum(1))[0,1])))
    pd.DataFrame(periodic).to_csv(OUT/'periodicity.csv',index=False)
    pd.DataFrame(monthly).to_csv(OUT/'monthly_savings.csv',index=False);pd.DataFrame(certs).to_csv(OUT/'new_solver_certificates.csv',index=False)
    dump_json(OUT/'improvement.json',gains)
    dump_json(OUT/'verification.json',dict(status='PASS',traces=audits,total_intervals=sum(x['intervals'] for x in audits),new_independent_lp_cases=len(certs),max_duality_gap=max(x['gap'] for x in certs),inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(a.data_root,'附件').glob('附件*.xlsx')},sources={str(p):hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in Path('src').glob('v5b_*.py')}))
    print('PASS',len(audits),'full traces;',len(certs),'independent LP certificates');print([(r['question'],r['cost'],r['saving']) for r in gains])
if __name__=='__main__':main()
