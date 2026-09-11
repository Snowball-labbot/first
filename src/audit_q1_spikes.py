"""Diagnose dispatch spikes without replacing the submitted schedule.

Hold discharge and unused supply fixed, and find a less variable charge
schedule on the same minimum-cost face. This is a diagnostic LP, not a new
primary objective or a smoothed picture of the original observations.
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from src.q12 import B, audit_trace, dump_json


def main():
    f = pd.read_csv('artifacts/q12/q1_intervals.csv')
    n = len(f)
    # Variables: charge energies followed by absolute successive differences.
    c = np.r_[np.zeros(n), np.ones(n-1)]
    cumulative = np.tril(np.ones((n,n)))
    fixed_soc = B.initial - np.cumsum(f.discharge_kwh.to_numpy()) / B.eta_d
    a = []; b = []
    for sign, rhs in [(1, B.maximum-fixed_soc), (-1, fixed_soc-B.minimum)]:
        a.extend(np.c_[sign*B.eta_c*cumulative, np.zeros((n,n-1))]); b.extend(rhs)
    for i in range(n-1):
        row = np.zeros(2*n-1); row[i+1]=1; row[i]=-1; row[n+i]=-1
        a.append(row); b.append(0)
        row=row.copy(); row[:n]*=-1; a.append(row); b.append(0)
    lower = np.maximum(0, f.charge_kwh.to_numpy()-f.plan_kwh.to_numpy())
    upper = np.where(f.discharge_kwh.to_numpy()>1e-7, 0, B.limit)
    res = linprog(c, A_ub=np.array(a), b_ub=np.array(b),
        A_eq=np.c_[np.vstack([np.ones(n),f.price]), np.zeros((2,n-1))],
        b_eq=[f.charge_kwh.sum(), np.dot(f.price,f.charge_kwh)],
        bounds=list(zip(lower,upper))+[(0,None)]*(n-1), method='highs')
    if not res.success: raise RuntimeError(res.message)
    alt=f.copy(); alt['charge_kwh']=res.x[:n]
    alt['plan_kwh']=f.plan_kwh+alt.charge_kwh-f.charge_kwh
    alt['soc_end_kwh']=B.initial+np.cumsum(B.eta_c*alt.charge_kwh-alt.discharge_kwh/B.eta_d)
    alt['soc_start_kwh']=np.r_[B.initial,alt.soc_end_kwh.iloc[:-1]]
    audit=audit_trace(alt, initial=B.initial)
    cost=float(np.dot(f.price,f.plan_kwh)); alt_cost=float(np.dot(alt.price,alt.plan_kwh))
    assert abs(alt_cost-cost)<1e-5 and abs(alt.soc_end_kwh.iloc[-1]-B.initial)<1e-5
    out=Path('artifacts/q12_revision');out.mkdir(exist_ok=True)
    intervals=[]
    for i in np.where(f.charge_kwh.to_numpy()*6>4999)[0]:
        intervals.append({'index':int(i),'hour':float(i/6),'price':float(f.price.iloc[i]),
            'grid_kw':float(f.plan_kwh.iloc[i]*6),'load_kw':float(f.load_kwh.iloc[i]*6),
            'pv_kw':float(f.pv_kwh.iloc[i]*6),'charge_kw':float(f.charge_kwh.iloc[i]*6)})
    result={'original_cost_yuan':cost,'alternative_cost_yuan':alt_cost,
        'original_charge_variation_kw':float(np.abs(np.diff(f.charge_kwh*6)).sum()),
        'alternative_charge_variation_kw':float(np.abs(np.diff(alt.charge_kwh*6)).sum()),
        'maximum_grid_change_kw':float(np.max(np.abs(alt.plan_kwh-f.plan_kwh))*6),
        'alternative_audit':audit,'full_charge_intervals':intervals,
        'interpretation':'With discharge and spill fixed, a same-cost charge-variation LP changes the schedule only at numerical precision. This does not establish nonuniqueness or uniqueness of the full MILP. Spikes align with charging at low prices; switching/ramp costs are absent. Original report/Excel schedule is retained.'}
    dump_json(out/'q1_spike_audit.json',result)
    print(result)


if __name__=='__main__':main()
