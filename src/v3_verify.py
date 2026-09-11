"""Reconstruct final contracts independently and compare all physical traces."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import pandas as pd
from src.q12 import audit_trace,dump_json,TOL
from src.q34_data import read_extended

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args()
    out=Path('artifacts/v3');data,_=read_extended(a.data_root);checks={}
    manifest=json.loads((out/'run_manifest.json').read_text(encoding='utf8'))
    for f,h in manifest['sources'].items():assert hashlib.sha256(Path(f).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h
    summaries=json.loads((out/'summary.json').read_text(encoding='utf8'))
    for s in summaries:
        name=s['strategy'];f=pd.read_csv(out/f'{name}_intervals.csv.gz');daily=pd.read_csv(out/f'{name}_daily.csv')
        assert len(f)==334*144 and len(daily)==334
        prices=np.tile(data['price'],334) if name.startswith('q3') else data['actual_price'][31:].reshape(-1)
        for col,expected in [('load_kwh',data['load'][31:].reshape(-1)),('pv_kwh',data['pv'][31:].reshape(-1)),('price',prices)]:
            np.testing.assert_allclose(f[col],expected,atol=1e-10,rtol=0)
        physical=audit_trace(f,initial=9902.811287870369)
        vp=out/f'{name}_versions.csv.gz';vs=pd.read_csv(vp) if vp.exists() else pd.DataFrame()
        groups={d:g for d,g in vs.groupby('date')} if len(vs) else {}
        for date,g in f.groupby('date',sort=False):
            plan=g.original_plan_kwh.to_numpy().copy()
            if date in groups:
                for ver,v in groups[date].groupby('version',sort=True):
                    slots=v.slot.to_numpy(int);np.testing.assert_array_equal(slots,np.arange(int(ver)*36,144))
                    np.testing.assert_allclose(v.old_kwh,plan[slots],atol=TOL,rtol=0)
                    np.testing.assert_allclose(v.decision_soc_kwh,g.soc_start_kwh.iloc[int(ver)*36],atol=TOL,rtol=0)
                    plan[slots]=v.new_kwh
            np.testing.assert_allclose(plan,g.plan_kwh,atol=TOL,rtol=0)
        # Independent formula uses retained quantity + positive penalties, not
        # the solver's original +/- accounting expression.
        x=f.original_plan_kwh.to_numpy();y=f.plan_kwh.to_numpy();u=np.maximum(x-y,0);v=np.maximum(y-x,0)
        np.testing.assert_allclose(f.decrease_kwh,u,atol=TOL,rtol=0);np.testing.assert_allclose(f.increase_kwh,v,atol=TOL,rtol=0)
        total=prices*(np.minimum(x,y)+.5*u+1.5*v+5*f.emergency_kwh.to_numpy())
        np.testing.assert_allclose(total,f.total_cost_yuan,atol=TOL,rtol=0)
        np.testing.assert_allclose(total.reshape(334,144).sum(1),daily.total_cost_yuan,atol=1e-6,rtol=0)
        assert abs(total.sum()-s['total_cost_yuan'])<1e-5
        for col in ['original_cost_yuan','increase_cost_yuan','decrease_cost_yuan','emergency_cost_yuan','total_cost_yuan']:
            assert abs(f[col].sum()-s[col])<1e-5
        solver=pd.read_csv(out/f'{name}_solvers.csv.gz');assert (solver.status==0).all()
        checks[name]={'physical':physical,'cost':float(total.sum()),'versions':len(vs),'solver_calls':len(solver)}
    assert len(checks)==16
    q1=pd.read_csv(out/'q1_intervals.csv');audit_trace(q1,initial=6000)
    for col,key in [('load_kwh','q1_load'),('pv_kwh','q1_pv'),('price','price')]:np.testing.assert_allclose(q1[col],np.roll(data[key],1),atol=1e-10)
    b=pd.read_csv(out/'nominal_price_bound.csv');assert len(b)==1002 and b.regret.min()>-1e-5
    # Paired GRU vs seasonal actual savings with temporal block dependence.
    df0=pd.read_csv(out/'q4_3_seasonal_daily.csv');df1=pd.read_csv(out/'q4_3_gru_mean_daily.csv')
    diff=(df0.total_cost_yuan-df1.total_cost_yuan).to_numpy();rng=np.random.default_rng(20260911);cis={}
    for length in [7,14,28]:
        starts=rng.integers(0,len(diff),(2000,int(np.ceil(len(diff)/length))))
        ids=((starts[:,:,None]+np.arange(length))%len(diff)).reshape(2000,-1)[:,:len(diff)]
        cis[str(length)]=np.quantile(diff[ids].sum(1),[.025,.975]).tolist()
    dump_json(out/'verification.json',{'pass':True,'traces':checks,'q1_pass':True,'nominal_bound_cases':len(b),
        'gru_saving_yuan':float(diff.sum()),'gru_saving_block95':cis,'daily_series_exact_order':True})
    print('PASS:16 full-year traces, final settlements, Q1 alignment, 1002 paired nominal cases',cis)

if __name__=='__main__':main()
