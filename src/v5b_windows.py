"""Training-window sensitivity, separated from policy selection."""
from pathlib import Path
import inspect,argparse
import numpy as np
import pandas as pd
import src.q12 as q12
from src.q34_data import read_extended


def window_forecasts(data,window):
    # Reuse the full checked forecaster, changing exactly one training horizon.
    source=inspect.getsource(q12.forecasts).replace('d-60','d-'+str(int(window)))
    namespace=dict(vars(q12));exec(compile(source,'<window_forecasts>','exec'),namespace)
    return namespace['forecasts'](data,'ridge',(1.,1.))[0]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args()
    out=Path('artifacts/v5b');data,_=read_extended(a.data_root);rows=[]
    q12.dump_json(out/'window_design.json',{'windows_days':[28,56,60,84],'same_model':'ridge alpha 1; weekly refit; all other features unchanged',
        'interpretation':'Sensitivity only; January cannot distinguish these windows because training starts on day 7. Do not pick lowest annual result as a validated policy.'})
    for window in [28,56,60,84]:
        pred=window_forecasts(data,window)
        val=q12.backtest(data,pred,21,31,6244.256891388887,.7,'validation',retain=False)[0]
        daily=q12.backtest(data,pred,31,365,9902.811287870369,.7,'window',retain=False)[0]
        row=dict(window_days=window,validation_cost=float(val.total_cost_yuan.sum()),annual_cost=float(daily.total_cost_yuan.sum()),
            load_mae_kwh=float(abs(pred['load'][31:]-data['load'][31:]).mean()),pv_mae_kwh=float(abs(pred['pv'][31:]-data['pv'][31:]).mean()))
        rows.append(row);print(row,flush=True)
    pd.DataFrame(rows).to_csv(out/'window_sensitivity.csv',index=False)
if __name__=='__main__':main()
