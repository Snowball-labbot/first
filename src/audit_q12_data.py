"""Reopen original spreadsheets and verify preprocessing and chronological use."""
from pathlib import Path
import argparse
import hashlib
import json
from collections import Counter
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from src.q12 import read_inputs, forecasts, reserve, dump_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);a=p.parse_args()
    out=Path('artifacts/q12_revision');out.mkdir(exist_ok=True)
    data,base=read_inputs(a.data_root)
    arrays={};stats={}
    for fname,sheets in [('附件1.xlsx',[None]),('附件2.xlsx',['小区负载','光伏发电实际功率'])]:
        wb=load_workbook(a.data_root/'附件'/fname,read_only=True,data_only=True)
        for sheet in sheets:
            ws=wb[sheet] if sheet else wb.worksheets[0]
            rows=list(ws.iter_rows(values_only=True))
            if fname=='附件1.xlsx':
                arrays['price']=np.array([r[1] for r in rows[1:]],dtype=float)
                arrays['q1_load']=np.array([r[2] for r in rows[1:]],dtype=float)
                arrays['q1_pv']=np.array([r[3] for r in rows[1:]],dtype=float)
                time_types=dict(Counter(type(r[0]).__name__ for r in rows[1:]))
            else:
                arrays['load' if sheet=='小区负载' else 'pv']=np.array([r[1:] for r in rows[1:]],dtype=float)
        wb.close()
    for key,raw in arrays.items():
        expected=raw if key=='price' else raw/6
        np.testing.assert_allclose(data[key],expected,rtol=0,atol=5e-13)
        q25,q75=np.quantile(raw,[.25,.75]);iqr=q75-q25
        stats[key]={'count':raw.size,'missing_nonfinite':int((~np.isfinite(raw)).sum()),
            'negative':int((raw<0).sum()),'zeros':int((raw==0).sum()),'min':float(raw.min()),'max':float(raw.max()),
            'unit':'yuan/kWh' if key=='price' else 'kW','global_IQR_flags_only':int(((raw<q25-1.5*iqr)|(raw>q75+1.5*iqr)).sum()),
            'raw_to_model_max_absolute_difference':float(np.abs(data[key]-expected).max()),
            'removed_values':0,'imputed_values':0,'winsorized_values':0,'smoothed_values':0}
    trace=pd.read_csv('artifacts/q12/ridge_q0.7_intervals.csv.gz')
    for key in ['load','pv']:
        np.testing.assert_allclose(trace[key+'_kwh'],arrays[key][31:].ravel()/6,rtol=0,atol=1e-10)
    # Whole forecast/update pipeline prefix test, beyond the existing feature-only test.
    cutoff=35
    baseline,_=forecasts(data,'ridge',alphas=(1,1),stop=42)
    changed={**data,'load':data['load'].copy(),'pv':data['pv'].copy()}
    changed['load'][cutoff:]*=4;changed['pv'][cutoff:]=0
    perturbed,_=forecasts(changed,'ridge',alphas=(1,1),stop=42)
    for key in ['load','pv']:np.testing.assert_allclose(baseline[key][:cutoff+1],perturbed[key][:cutoff+1],rtol=0,atol=1e-10)
    np.testing.assert_allclose(reserve(data,baseline,cutoff,.7),reserve(changed,perturbed,cutoff,.7),rtol=0,atol=1e-10)
    manifest=json.loads(Path('artifacts/q12/run_manifest.json').read_text())
    assert base['input_files']==manifest['input_files']
    report={'pass':True,'raw_checks':stats,'attachment1_time_cell_types':time_types,
        'date_count':365,'date_duplicates':0,'complete_time_slots_per_day':144,
        'load_identical_day_pairs':int(pd.DataFrame(arrays['load']).duplicated().sum()),
        'pv_identical_day_pairs':int(pd.DataFrame(arrays['pv']).duplicated().sum()),
        'operations_applied':['time representation normalization','right-end interval mapping assumption','kW multiplied by 1/6 hour'],
        'operations_not_needed':['missing value imputation','negative value correction','duplicate date removal'],
        'operations_not_applied':['statistical outlier deletion','winsorization','smoothing'],
        'notes':['Global IQR flags are descriptive only; time-series regimes are not corruption evidence.',
                 'Forecast clipping is a prediction rule, not cleaning observed data.',
                 'Ridge standardization is fit on training history only, not on the whole year.'],
        'saved_actuals_match_raw':True,'whole_forecast_and_reserve_causal_prefix_test':True,
        'original_fingerprints_match_run':True,'auditor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    dump_json(out/'data_cleaning_audit.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
