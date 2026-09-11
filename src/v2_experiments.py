"""January-only selection, full-year paired ablations and frozen V2 policies."""
from pathlib import Path
from dataclasses import asdict
import argparse,hashlib,json,time,platform
import numpy as np
import pandas as pd
import scipy
from src.q12 import forecasts,dump_json,optimize_day
from src.q34_data import read_extended
from src.v2_model import Policy,corrected_load,risk_buffers,run,solve


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True)
    ap.add_argument('--out',type=Path,default=Path('artifacts/v2'));ap.add_argument('--smoke',action='store_true')
    args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    data,audit=read_extended(args.data_root);pred,fits=forecasts(data,'ridge',(1.,1.))
    price=np.load('artifacts/q34/price_forecasts.npz');sval=6244.256891388887;s0=9902.811287870369
    stop=38 if args.smoke else 365
    contract={'q2_quantiles':[0.,.5,.7,.8,.9],'q2_terminals':[1200.,6000.,9000.],
        'q3_quantiles':[0.,.5,.7],'q3_betas':[0.,.5,1.],'q3_masks':[6,7],
        'q3_terminal':6000.,'bias_lookback_slots':18,'bias_decay_slots':36,
        'price_models':['seasonal','ridge','gru_mean'],'validation':[21,31],'evaluation':[31,stop],
        'selection':'January realized total cost; ties use smaller complexity, no evaluation-based retuning',
        'scope':'Within-dataset revision; old full-year metrics were already inspected. Not new external validation.'}
    dump_json(out/'design_before_evaluation.json',contract)
    loads={b:corrected_load(data,pred,b) for b in contract['q3_betas']}
    pv2=np.repeat(pred['pv'][:,None,:],4,axis=1);pv3=data['pv_issued'];cache={}
    def inputs(mode,policy,until):
        key=(mode,policy.beta,policy.quantile,until)
        pp=pv2 if mode==2 else pv3;ll=loads[policy.beta]
        if key not in cache:
            cache[key]=risk_buffers(data,ll[:until],pp[:until],policy.quantile)
        return ll,pp,cache[key]
    def calc(mode,pol,start,end,name,prices=None,retain=False):
        ll,pp,rr=inputs(mode,pol,end)
        return run(data,ll,pp,rr,pol,start=start,stop=end,initial=sval if start==21 else s0,
                   name=name,prices=prices,retain=retain)
    selected={};validation=[]
    for mode in [2,3]:
        if mode==2:
            policies=[Policy(quantile=q,terminal=t) for q in contract['q2_quantiles'] for t in contract['q2_terminals']]
        else:
            policies=[Policy(quantile=q,beta=b,mask=m) for q in contract['q3_quantiles']
                      for b in contract['q3_betas'] for m in contract['q3_masks']]
        rows=[]
        for pol in policies:
            result=calc(mode,pol,21,31,f'q{mode}_validation')
            rows.append({**asdict(pol),'cost':result[3]['total_cost_yuan'],'final_soc':result[3]['final_soc'],
                         'emergency_kwh':result[3]['emergency_kwh']})
        best=min(rows,key=lambda x:(x['cost'],x['beta'],x['mask'],x['quantile'],x['terminal']))
        selected[str(mode)]=Policy(**{k:best[k] for k in asdict(Policy())})
        validation.extend([{'mode':mode,**r} for r in rows])
        print('JANUARY SELECTION',mode,best,flush=True)
    pd.DataFrame(validation).to_csv(out/'validation.csv',index=False,float_format='%.17g')
    price_validation=[];price_selected={}
    for mode in [2,3]:
        for model in contract['price_models']:
            r=calc(mode,selected[str(mode)],21,31,f'q4_{mode}_{model}',price[model])
            price_validation.append({'mode':mode,'model':model,'cost':r[3]['total_cost_yuan'],'final_soc':r[3]['final_soc']})
        price_selected[str(mode)]=min([r for r in price_validation if r['mode']==mode],key=lambda x:x['cost'])['model']
    dump_json(out/'selection.json',{'policies':{k:asdict(v) for k,v in selected.items()},'prices':price_selected,
        'frozen_before_evaluation':True,'validation_initial_soc':sval,'evaluation_initial_soc':s0})
    pd.DataFrame(price_validation).to_csv(out/'price_validation.csv',index=False,float_format='%.17g')
    q1,m=solve(data['q1_load'],data['q1_pv'],data['price'],6000,equal=True)
    q1.insert(0,'slot',range(144));q1.to_csv(out/'q1_intervals.csv',index=False,float_format='%.17g')
    _,oldm=optimize_day(data['q1_load'],data['q1_pv'],data['price'],6000,(6000,'equal'))
    assert abs(m['objective']-oldm['cost'])<1e-5
    dump_json(out/'q1_comparison.json',{'lp':m,'milp':oldm,'absolute_cost_difference':abs(m['objective']-oldm['cost'])})
    summaries=[]
    def save(mode,pol,label,prices=None):
        r=calc(mode,pol,31,stop,label,prices,True)
        daily,trace,versions,summary,solver=r
        daily.to_csv(out/f'{label}_daily.csv',index=False,float_format='%.17g')
        trace.to_csv(out/f'{label}_intervals.csv.gz',index=False,float_format='%.17g')
        if len(versions):versions.to_csv(out/f'{label}_versions.csv.gz',index=False,float_format='%.17g')
        solver.to_csv(out/f'{label}_solvers.csv.gz',index=False,float_format='%.17g')
        dump_json(out/f'{label}_summary.json',summary);summaries.append(summary)
        print('EVALUATED',label,round(summary['total_cost_yuan'],2),'emergency',round(summary['emergency_kwh'],2),flush=True)
    # LP-only controls distinguish solver equivalence from forecast/policy gains.
    save(2,Policy(),'q2_lp_control')
    save(3,Policy(quantile=0,mask=6),'q3_lp_control')
    save(2,selected['2'],'q2_v2')
    save(3,selected['3'],'q3_v2')
    p=selected['3'];save(3,Policy(**{**asdict(p),'beta':1. if p.beta==0 else 0.}),'q3_bias_ablation')
    save(3,Policy(**{**asdict(p),'refund':False}),'q3_no_refund')
    for mode in [2,3]:
        for model in contract['price_models']:
            save(mode,selected[str(mode)],f'q4_{mode}_{model}',price[model])
    dump_json(out/'summary.json',summaries)
    # Same target clocks, separate release metrics; do not count repeated targets as independent.
    metrics=[]
    for model in ['seasonal','ridge','gru17','gru42','gru2026','gru_mean']:
        for version in range(4):
            actual=data['actual_price'][31:stop,version*36:]
            err=price[model][31:stop,version,:actual.shape[1]]-actual
            metrics.append({'model':model,'issue_hour':6*version,'n_pairs':err.size,
                'mae':float(np.abs(err).mean()),'rmse':float(np.sqrt((err*err).mean()))})
    pd.DataFrame(metrics).to_csv(out/'price_errors_by_issue.csv',index=False,float_format='%.17g')
    dump_json(out/'run_manifest.json',{'stage':'smoke' if args.smoke else 'full','seconds':time.perf_counter()-started,
        'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,'input_files':audit['input_files'],
        'source_sha256':{s:hashlib.sha256(Path(s).read_bytes()).hexdigest() for s in ['src/v2_model.py','src/v2_experiments.py']},
        'forecast_archive_sha256':hashlib.sha256(Path('artifacts/q34/price_forecasts.npz').read_bytes()).hexdigest(),
        'load_pv_forecast_fits':fits,'design':contract})
    print('COMPLETE',round(time.perf_counter()-started,2),flush=True)


if __name__=='__main__':main()
