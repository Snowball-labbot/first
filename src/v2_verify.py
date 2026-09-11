"""Independent saved-output audit; raw XLSX equality, accounting and paired effects."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
import pandas as pd
from src.q12 import B,TOL,dump_json,audit_trace
from src.q34_data import read_extended


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True)
    ap.add_argument('--out',type=Path,default=Path('artifacts/v2'));args=ap.parse_args();out=args.out
    data,raw=read_extended(args.data_root);checks={}
    manifest=json.loads((out/'run_manifest.json').read_text(encoding='utf8'))
    assert manifest['stage']=='full'
    for file,h in manifest['source_sha256'].items():assert hashlib.sha256(Path(file).read_bytes()).hexdigest()==h
    for path in sorted(out.glob('*_intervals.csv.gz')):
        name=path.name.removesuffix('_intervals.csv.gz');f=pd.read_csv(path)
        s=json.loads((out/f'{name}_summary.json').read_text());d=pd.read_csv(out/f'{name}_daily.csv')
        assert len(f)==334*144 and f.date.nunique()==334
        np.testing.assert_array_equal(f.date,np.repeat(data['dates'][31:].strftime('%Y-%m-%d'),144))
        np.testing.assert_array_equal(f.slot,np.tile(np.arange(144),334))
        for k in ['load','pv']:np.testing.assert_allclose(f[k+'_kwh'],data[k][31:].ravel(),rtol=0,atol=1e-8)
        prices=data['actual_price'][31:].ravel() if name.startswith('q4') else np.tile(data['price'],334)
        np.testing.assert_allclose(f.price,prices,rtol=0,atol=1e-12)
        physical=audit_trace(f,initial=s['initial_soc'])
        vp=out/f'{name}_versions.csv.gz';v=pd.read_csv(vp) if vp.exists() else pd.DataFrame()
        groups={date:g for date,g in v.groupby('date')} if len(v) else {}
        for date,g in f.groupby('date',sort=False):
            plan=g.original_plan_kwh.to_numpy().copy();up=np.zeros(144);down=np.zeros(144)
            if date in groups:
                for ver,items in groups[date].groupby('version',sort=True):
                    first=int(ver)*36;slots=items.slot.to_numpy(int)
                    np.testing.assert_array_equal(slots,np.arange(first,144))
                    assert (items.effective_slot==first).all()
                    np.testing.assert_allclose(items.old_kwh,plan[slots],atol=TOL,rtol=0)
                    np.testing.assert_allclose(items.decision_soc_kwh,g.soc_start_kwh.iloc[first],atol=TOL,rtol=0)
                    delta=items.new_kwh.to_numpy()-plan[slots]
                    np.testing.assert_allclose(items.increase_kwh,np.maximum(delta,0),atol=TOL,rtol=0)
                    np.testing.assert_allclose(items.decrease_kwh,np.maximum(-delta,0),atol=TOL,rtol=0)
                    up[slots]+=np.maximum(delta,0);down[slots]+=np.maximum(-delta,0);plan[slots]=items.new_kwh
            for a,b in [(plan,g.plan_kwh),(up,g.increase_kwh),(down,g.decrease_kwh)]:
                np.testing.assert_allclose(a,b,atol=TOL,rtol=0)
        coeff=-.5 if s['policy']['refund'] else .5
        pieces={'original_cost_yuan':prices*f.original_plan_kwh,'increase_cost_yuan':prices*1.5*f.increase_kwh,
                'decrease_cost_yuan':prices*coeff*f.decrease_kwh,'emergency_cost_yuan':prices*5*f.emergency_kwh}
        pieces['total_cost_yuan']=sum(pieces.values())
        for key,values in pieces.items():
            np.testing.assert_allclose(f[key],values,rtol=0,atol=TOL)
            np.testing.assert_allclose(d[key],f.groupby('date',sort=False)[key].sum(),rtol=0,atol=TOL)
            assert abs(float(values.sum())-s[key])<1e-5
        ss=pd.read_csv(out/f'{name}_solvers.csv.gz');assert (ss.status==0).all()
        checks[name]={'pass':True,'physical':physical,'solves':len(ss),'revision_rows':len(v),'cost':s['total_cost_yuan']}
    assert len(checks)==12
    q1=pd.read_csv(out/'q1_intervals.csv');audit_trace(q1,initial=6000)
    assert abs(q1.soc_end_kwh.iloc[-1]-6000)<TOL
    assert abs(np.dot(q1.plan_kwh,data['price'])-json.loads(Path('artifacts/q12/q1_summary.json').read_text())['cost'])<TOL
    # Pair days, retain autocorrelation within circular blocks; empirical uncertainty only.
    sel=json.loads((out/'selection.json').read_text());comparison=[];monthly=[];rng=np.random.default_rng(20260911)
    mappings={'q2':('q2_v2','artifacts/q12/ridge_q0.7_intervals.csv.gz'),
              'q3':('q3_v2','artifacts/q34/q3_m6_intervals.csv.gz'),
              'q4-2':(f'q4_2_{sel["prices"]["2"]}','artifacts/q34/q4_2_ridge_intervals.csv.gz'),
              'q4-3':(f'q4_3_{sel["prices"]["3"]}','artifacts/q34/q4_3_seasonal_intervals.csv.gz')}
    for key,(new,oldpath) in mappings.items():
        before=pd.read_csv(oldpath);after=pd.read_csv(out/f'{new}_intervals.csv.gz')
        if 'total_cost_yuan' not in before:before['total_cost_yuan']=before.price*(before.plan_kwh+5*before.emergency_kwh)
        c0=before.groupby('date',sort=False).total_cost_yuan.sum();c1=after.groupby('date',sort=False).total_cost_yuan.sum()
        assert c0.index.equals(c1.index)
        diff=(c0-c1).to_numpy();ci={}
        for block in [7,14,28]:
            starts=rng.integers(0,len(diff),(2000,int(np.ceil(len(diff)/block))))
            idx=((starts[:,:,None]+np.arange(block))%len(diff)).reshape(2000,-1)[:,:len(diff)]
            totals=diff[idx].mean(axis=1)*len(diff)
            ci[str(block)]=[float(x) for x in np.quantile(totals,[.025,.975])]
        endgap=float(before.soc_end_kwh.iloc[-1]-after.soc_end_kwh.iloc[-1])
        # Accounting stress range only: no actual post-year trades are fabricated.
        replacement=max(endgap,0)/B.eta_c*float(data['actual_price'].max() if key.startswith('q4') else data['price'].max())
        comparison.append({'question':key,'candidate':new,'v1_cost':float(c0.sum()),'candidate_cost':float(c1.sum()),
            'saving_yuan':float(diff.sum()),'saving_percent':float(diff.sum()/c0.sum()*100),
            'v1_final_soc':float(before.soc_end_kwh.iloc[-1]),'candidate_final_soc':float(after.soc_end_kwh.iloc[-1]),
            'terminal_inventory_stress_yuan':replacement,'saving_after_inventory_stress':float(diff.sum()-replacement),
            'block_bootstrap_95pct':ci,'winning_days':int((diff>0).sum()),'losing_days':int((diff<0).sum())})
        for month,g in pd.DataFrame({'date':c0.index,'v1':c0.to_numpy(),'candidate':c1.to_numpy()}).groupby(lambda i:c0.index[i][:7]):
            monthly.append({'question':key,'month':month,'v1':float(g.v1.sum()),'candidate':float(g.candidate.sum()),'saving':float((g.v1-g.candidate).sum())})
    dump_json(out/'paired_comparison.json',comparison);pd.DataFrame(monthly).to_csv(out/'monthly_comparison.csv',index=False,float_format='%.17g')
    dump_json(out/'verification.json',{'pass':True,'traces':checks,'q1_pass':True,'input_files':raw['input_files'],
        'uncertainty_note':'Circular paired-day bootstrap; assumes block exchangeability, not an external-year confidence guarantee; length sensitivity 7/14/28 days.',
        'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    print(json.dumps(comparison,ensure_ascii=False,indent=2));print('PASS: 12 full-year traces + Q1; all saved costs, revisions, physical constraints and source hashes')


if __name__=='__main__':main()
