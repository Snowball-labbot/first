"""Bind V7 figures to archived dispatch and reconstructed non-neural prices."""
from pathlib import Path
import json, hashlib, shutil
import numpy as np
import pandas as pd
from scipy.io import savemat
from src.q12 import audit_trace
from src.q34_data import read_extended
from src.v7_price import residual_bands

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT/'artifacts/v7'; out.mkdir(exist_ok=True)
    data, raw_audit = read_extended(ROOT.parent/'CUMCM2026Problems/C题')
    forecasts = np.load(out/'price_forecasts.npz')
    d = dict(price=data['actual_price'], hours=(np.arange(144)+.5)/6,
             price_ridge=forecasts['ridge'], price_seasonal=forecasts['seasonal'])
    q1 = json.loads((ROOT/'artifacts/v3/q1_summary.json').read_text())
    efficiency = pd.read_csv(ROOT/'artifacts/v3/q1_efficiency.csv')
    d['q1_efficiency'] = efficiency.roundtrip_efficiency.to_numpy()*100
    d['q1_sensitivity'] = efficiency.cost.to_numpy()/1e4
    d['q1_waterfall'] = np.array([q1['no_storage_cost'], efficiency.cost.iloc[-1], q1['cost']])/1e4
    summaries = {s['strategy']:s for s in json.loads((ROOT/'artifacts/v3/summary.json').read_text())}
    d['q3_cost'] = np.array([summaries[f'q3_m{i}']['total_cost_yuan'] for i in range(8)])/1e4
    improvement = json.loads((ROOT/'artifacts/v5b/improvement.json').read_text())
    d['q3_evolution'] = np.array([summaries['q3_m7']['total_cost_yuan'], improvement[1]['baseline_cost'], improvement[1]['cost']])/1e4
    sources = json.loads((ROOT/'artifacts/v5b/delivery_selection.json').read_text())['sources']
    traces = {}; audits = {}; components = []; totals = []
    for key, path in sources.items():
        f = pd.read_csv(ROOT/path.replace('\\','/'))
        physical = audit_trace(f, initial=float(f.soc_start_kwh.iloc[0]))
        if key == '1':
            cost = float((f.price*f.plan_kwh).sum())
        else:
            p = f.price.to_numpy(); original = f.original_plan_kwh if 'original_plan_kwh' in f else f.plan_kwh
            inc = np.maximum(f.plan_kwh-original, 0); dec = np.maximum(original-f.plan_kwh, 0)
            kept = np.minimum(original, f.plan_kwh)
            bill = p*kept + .5*p*dec + 1.5*p*inc + 5*p*f.emergency_kwh
            np.testing.assert_allclose(bill, f.total_cost_yuan, atol=1e-7)
            cost = float(bill.sum())
            if key.startswith('4'):
                components.append([float(np.sum(p*kept)),float(np.sum(.5*p*dec)),float(np.sum(1.5*p*inc)),float(np.sum(5*p*f.emergency_kwh))])
                totals.append(cost)
        audits[key] = dict(cost_yuan=cost, rows=len(f), physical=physical,
            initial=float(f.soc_start_kwh.iloc[0]), final=float(f.soc_end_kwh.iloc[-1]))
        traces[key] = f
        shutil.copyfile(ROOT/f'artifacts/v5b/result{key}.xlsx', out/f'result{key}.xlsx')
    d['q4_components'] = np.array(components)/1e4; d['q4_totals'] = np.array(totals)/1e4
    month_savings = pd.read_csv(ROOT/'artifacts/v5b/monthly_savings.csv')
    d['q4_month_savings'] = np.array([month_savings.loc[month_savings.question.astype(str)==key,'saving'].to_numpy() for key in ['4-2','4-3']])/1e4
    d['q4_savings'] = np.array([r['saving'] for r in improvement[2:]])/1e4
    d['q4_ci'] = np.array([[next(b for b in r['bootstrap'] if b['block']==14)[k] for k in ['low','high']] for r in improvement[2:]])/1e4
    bands = residual_bands(data['actual_price'], forecasts['ridge'])
    days = [int((pd.Timestamp(x)-data['dates'][0]).days) for x in ['2025-03-20','2025-06-21','2025-09-23','2025-12-21']]
    d['specified_days'] = np.array(days)+1
    d['specified_price'] = data['actual_price'][days]
    d['specified_forecast'] = forecasts['ridge'][days,0]
    d['specified_lower'] = bands[0][days]; d['specified_upper'] = bands[1][days]
    actual = data['actual_price'][31:]; inside=(actual>=bands[0][31:])&(actual<=bands[1][31:])
    d['price_band_coverage'] = float(inside.mean())
    for key,name in [('4-2','dayahead'),('4-3','rolling')]:
        f=traces[key]
        for column in ['soc_start_kwh','charge_kwh','discharge_kwh','plan_kwh','emergency_kwh']:
            d[name+'_'+column] = f[column].to_numpy().reshape(334,144)[np.array(days)-31]
    savemat(out/'figure_data.mat', d)
    source_files = list(sources.values())+['artifacts/v3/q1_summary.json','artifacts/v3/q1_efficiency.csv',
        'artifacts/v3/summary.json','artifacts/v5b/improvement.json','artifacts/v5b/monthly_savings.csv','artifacts/v7/price_forecasts.npz']
    report=dict(status='PASS', dispatch=audits, price_band_coverage=float(inside.mean()),
        bill_components_yuan=np.array(components).tolist(), q4_rolling_saving=totals[0]-totals[1],
        input_hashes={p.replace('\\','/'):hashlib.sha256((ROOT/p.replace('\\','/')).read_bytes()).hexdigest() for p in source_files},
        uncertainty='Point forecasts drive decisions; trailing 28-day residual ranges diagnose forecast uncertainty. No coverage guarantee or stochastic optimality claim.',
        raw_audit=raw_audit)
    (out/'evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k in ['status','price_band_coverage','bill_components_yuan','q4_rolling_saving']},ensure_ascii=False))


if __name__=='__main__':main()
