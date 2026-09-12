"""Frozen two-candidate audit experiment; no full-year strategy reselection."""
from pathlib import Path
import argparse,hashlib,time,json
import numpy as np
import pandas as pd
from src.q12 import forecasts,dump_json
from src.q34_data import read_extended
from src.v3_model import Policy,run,risk_buffers
from src.v5_model import adaptive_load

OUT=Path('artifacts/v5')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);tick=time.perf_counter()
    design={'candidates':['baseline','adaptive'],'validation_days':[21,31],'evaluation_days':[31,365],
        'window_days':28,'shrink':.2,'slope_bounds':[0,1.5],'observation_slots':18,'target_block_slots':6,
        'quantile':.5,'mask':7,'terminal':6000,'price_model':'seasonal',
        'selection':'January 22-31 realized cost separately for Q3 and Q4 rolling; baseline wins ties',
        'scope':'Same-dataset development; previous annual results known; no untouched-test claim'}
    dump_json(OUT/'design_before_evaluation.json',design)
    data,audit=read_extended(a.data_root);pred,fits=forecasts(data,'ridge',(1.,1.))
    base=np.repeat(pred['load'][:,None,:],4,axis=1)
    adaptive,records=adaptive_load(data,pred['load']);loads={'baseline':base,'adaptive':adaptive}
    pd.DataFrame(records).to_csv(OUT/'load_calibration.csv.gz',index=False,float_format='%.17g')
    prices=np.load('artifacts/q34/price_forecasts.npz')['seasonal'];pol=Policy(quantile=.5,mask=7)
    # Complete validation and record selections BEFORE building evaluation buffers.
    validation=[];chosen={}
    for mode in [3,4]:
        for name,ll in loads.items():
            rr=risk_buffers(data,ll[:31],data['pv_issued'][:31],.5)
            r=run(data,ll,data['pv_issued'],rr,pol,start=21,stop=31,initial=6244.256891388887,
                name=f'q{mode}_{name}',prices=prices if mode==4 else None,retain=False)
            validation.append(dict(mode=mode,candidate=name,cost=r[3]['total_cost_yuan'],final_soc=r[3]['final_soc']))
        chosen[str(mode)]=min([x for x in validation if x['mode']==mode],key=lambda x:(x['cost'],x['candidate']!='baseline'))['candidate']
    pd.DataFrame(validation).to_csv(OUT/'validation.csv',index=False)
    dump_json(OUT/'selection.json',chosen);print('January selection',chosen,validation,flush=True)
    summaries=[];daily_results={}
    for name,ll in loads.items():
        rr=risk_buffers(data,ll,data['pv_issued'],.5)
        for mode in [3,4]:
            label=f'q{mode}_{name}'
            r=run(data,ll,data['pv_issued'],rr,pol,start=31,stop=365,initial=9902.811287870369,
                name=label,prices=prices if mode==4 else None,retain=True)
            for obj,suffix in zip([r[0],r[1],r[2],r[4]],['daily.csv','intervals.csv.gz','versions.csv.gz','solvers.csv.gz']):
                obj.to_csv(OUT/f'{label}_{suffix}',index=False,float_format='%.17g')
            dump_json(OUT/f'{label}_summary.json',r[3]);summaries.append(r[3]);daily_results[label]=r[0]
            print(label,round(r[3]['total_cost_yuan'],2),flush=True)
    dump_json(OUT/'summary.json',summaries)
    metrics=[]
    for name,ll in loads.items():
        for v in [1,2,3]:
            e=ll[31:,v,36*v:]-data['load'][31:,36*v:]
            metrics.append(dict(candidate=name,issue_hour=6*v,mae_kwh=float(abs(e).mean()),rmse_kwh=float(np.sqrt((e*e).mean())),n_pairs=e.size))
    pd.DataFrame(metrics).to_csv(OUT/'load_errors.csv',index=False)
    pairs=[];rng=np.random.default_rng(20260912)
    for mode in [3,4]:
        b=daily_results[f'q{mode}_baseline'];c=daily_results[f'q{mode}_adaptive'];diff=b.total_cost_yuan.to_numpy()-c.total_cost_yuan.to_numpy()
        for block in [7,14,28]:
            starts=rng.integers(0,len(diff),(2000,int(np.ceil(len(diff)/block))))
            indices=((starts[:,:,None]+np.arange(block))%len(diff)).reshape(2000,-1)[:,:len(diff)]
            lo,hi=np.quantile(diff[indices].sum(axis=1),[.025,.975])
            pairs.append(dict(mode=mode,block_days=block,saving_yuan=float(diff.sum()),ci_low=float(lo),ci_high=float(hi),
                final_soc_difference_kwh=float(c.soc_end_kwh.iloc[-1]-b.soc_end_kwh.iloc[-1])))
    pd.DataFrame(pairs).to_csv(OUT/'paired_comparison.csv',index=False)
    dump_json(OUT/'run_manifest.json',dict(seconds=time.perf_counter()-tick,input_audit=audit,forecast_fits=fits,
        sources={f:hashlib.sha256(Path(f).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for f in
        ['src/v5_model.py','src/v5_experiments.py','src/v3_model.py','src/q12.py','src/q34_data.py']},
        price_cache_sha256=hashlib.sha256(Path('artifacts/q34/price_forecasts.npz').read_bytes()).hexdigest()))
if __name__=='__main__':main()
