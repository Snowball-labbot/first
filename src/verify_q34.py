"""Read saved Q3/Q4 traces and reconstruct every plan revision and bill."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
import pandas as pd
from src.q12 import audit_trace,TOL,dump_json
from src.q34_data import read_extended


def main():
    p=argparse.ArgumentParser();p.add_argument('--data-root',required=True)
    p.add_argument('--out',type=Path,default=Path('artifacts/q34'));args=p.parse_args();out=args.out
    data,raw=read_extended(args.data_root);checks={}
    for path in sorted(out.glob('*_intervals.csv.gz')):
        name=path.name.removesuffix('_intervals.csv.gz');f=pd.read_csv(path)
        assert len(f)==334*144 and f.date.nunique()==334
        expected_dates=np.repeat(data['dates'][31:].strftime('%Y-%m-%d'),144)
        np.testing.assert_array_equal(f.date.to_numpy(),expected_dates)
        np.testing.assert_array_equal(f.slot,np.tile(np.arange(144),334))
        for key in ['load','pv']:np.testing.assert_allclose(f[key+'_kwh'],data[key][31:].ravel(),atol=1e-8,rtol=0)
        price=np.tile(data['price'],334) if name.startswith('q3_') else data['actual_price'][31:].ravel()
        np.testing.assert_allclose(f.price,price,atol=1e-12,rtol=0)
        physical=audit_trace(f,initial=9902.811287870369)
        daily=pd.read_csv(out/f'{name}_daily.csv');summary=json.loads((out/f'{name}_summary.json').read_text())
        versions_path=out/f'{name}_versions.csv.gz'
        versions=pd.read_csv(versions_path) if versions_path.exists() else pd.DataFrame()
        ledger_groups={date:g for date,g in versions.groupby('date')} if len(versions) else {}
        for date,g in f.groupby('date',sort=False):
            plan=g.original_plan_kwh.to_numpy().copy();up=np.zeros(144);down=np.zeros(144)
            if date in ledger_groups:
                for v,items in ledger_groups[date].groupby('version',sort=True):
                    start=int(v)*36;slots=items.slot.to_numpy(int)
                    np.testing.assert_array_equal(slots,np.arange(start,144))
                    assert (items.effective_slot==start).all()
                    np.testing.assert_allclose(items.old_kwh,plan[slots],atol=TOL,rtol=0)
                    np.testing.assert_allclose(items.decision_soc_kwh,g.soc_start_kwh.iloc[start],atol=TOL,rtol=0)
                    delta=items.new_kwh.to_numpy()-plan[slots]
                    np.testing.assert_allclose(items.increase_kwh,np.maximum(delta,0),atol=TOL,rtol=0)
                    np.testing.assert_allclose(items.decrease_kwh,np.maximum(-delta,0),atol=TOL,rtol=0)
                    up[slots]+=np.maximum(delta,0);down[slots]+=np.maximum(-delta,0);plan[slots]=items.new_kwh
            np.testing.assert_allclose(plan,g.plan_kwh,atol=TOL,rtol=0)
            np.testing.assert_allclose(up,g.increase_kwh,atol=TOL,rtol=0)
            np.testing.assert_allclose(down,g.decrease_kwh,atol=TOL,rtol=0)
        coefficient=-.5 if summary['refund'] else .5
        bill=price*(f.original_plan_kwh+1.5*f.increase_kwh+coefficient*f.decrease_kwh+5*f.emergency_kwh)
        np.testing.assert_allclose(f.total_cost_yuan,bill,atol=TOL,rtol=0)
        np.testing.assert_allclose(daily.total_cost_yuan,f.groupby('date',sort=False).total_cost_yuan.sum(),atol=TOL,rtol=0)
        assert abs(float(bill.sum())-summary['total_cost_yuan'])<1e-5
        checks[name]={'pass':True,'physical':physical,'revision_rows':len(versions),'total_cost_yuan':float(bill.sum()),
            'trace_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    assert len(checks)>=20,len(checks)
    logs=json.loads((out/'price_fit_log.json').read_text())
    for log in logs:
        assert log['last_target_exclusive']<=log['fit_day']*144
        assert log['training_windows']>0 and log['inner_validation_windows']>0
    for f in ['q3_run_manifest.json','q4_run_manifest.json']:
        m=json.loads((out/f).read_text());assert m['stage']=='full'
        for source,h in m['source_sha256'].items():assert hashlib.sha256(Path(source).read_bytes()).hexdigest()==h
    dump_json(out/'verification.json',{'pass':True,'traces':checks,'price_model_fits':len(logs),
        'input_files':raw['input_files'],'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    print(f'PASS: {len(checks)} saved full-year traces, plan histories, actual input equality, physical constraints, all bills and {len(logs)} training cutoffs.')


if __name__=='__main__':main()
