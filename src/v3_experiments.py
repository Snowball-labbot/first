"""Final-versus-midnight settlement and paired price-information experiments."""
from pathlib import Path
import argparse,json,time,hashlib
import numpy as np
import pandas as pd
from src.q12 import forecasts,dump_json
from src.q34_data import read_extended
from src.v3_model import Policy,corrected_load,risk_buffers,run,solve

OUT=Path('artifacts/v3')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);beg=time.perf_counter()
    data,audit=read_extended(a.data_root);pred,_=forecasts(data,'ridge',(1.,1.))
    pp=np.load('artifacts/q34/price_forecasts.npz');ll=corrected_load(data,pred,0)
    pv2=np.repeat(pred['pv'][:,None,:],4,axis=1);pv3=data['pv_issued']
    cache={}
    def calc(mode,policy,start,stop,label,prices=None,save=False):
        pv=pv2 if mode==2 else pv3;k=(mode,policy.quantile,stop)
        if k not in cache:cache[k]=risk_buffers(data,ll[:stop],pv[:stop],policy.quantile)
        r=run(data,ll,pv,cache[k],policy,start=start,stop=stop,
            initial=6244.256891388887 if start==21 else 9902.811287870369,
            name=label,prices=prices,retain=save)
        if save:
            for obj,suffix in zip([r[0],r[1],r[2],r[4]],['daily.csv','intervals.csv.gz','versions.csv.gz','solvers.csv.gz']):
                if len(obj):obj.to_csv(OUT/f'{label}_{suffix}',index=False,float_format='%.17g')
            dump_json(OUT/f'{label}_summary.json',r[3]);print(label,round(r[3]['total_cost_yuan'],2),flush=True)
        return r
    # Fixed design preceding the new evaluation: exact Q3 mechanism, three risks,
    # all update subsets; Q4 fair price comparison with unchanged physical policy.
    design={'q3_quantiles':[0,.5,.7],'q3_masks':list(range(8)),'q4_models':['seasonal','ridge','gru_mean'],
        'q4_2_policy':{'quantile':.7,'terminal':6000},'settlement':'final vs midnight; no fees for intermediate reversals',
        'scope':'same-year revision; no claim of untouched external test set'}
    dump_json(OUT/'design.json',design);rows=[]
    for q in design['q3_quantiles']:
        for mask in range(8):
            r=calc(3,Policy(quantile=q,mask=mask),21,31,'validation')
            rows.append({'q':q,'mask':mask,'cost':r[3]['total_cost_yuan']})
    pd.DataFrame(rows).to_csv(OUT/'q3_validation.csv',index=False)
    best=min(rows,key=lambda x:(x['cost'],x['mask'],x['q']));pol=Policy(quantile=best['q'],mask=best['mask'])
    pvals=[]
    for mode in [2,3]:
        for m in design['q4_models']:
            r=calc(mode,Policy() if mode==2 else pol,21,31,'validation',pp[m])
            pvals.append({'mode':mode,'model':m,'cost':r[3]['total_cost_yuan']})
    selected={str(mode):min([r for r in pvals if r['mode']==mode],key=lambda x:x['cost'])['model'] for mode in [2,3]}
    dump_json(OUT/'selection.json',{'q3':best,'prices':selected});pd.DataFrame(pvals).to_csv(OUT/'q4_validation.csv',index=False)
    summaries=[]
    for mask in range(8):summaries.append(calc(3,Policy(quantile=pol.quantile,mask=mask),31,365,f'q3_m{mask}',save=True)[3])
    for mode in [2,3]:
        for m in design['q4_models']:
            summaries.append(calc(mode,Policy() if mode==2 else pol,31,365,f'q4_{mode}_{m}',pp[m],True)[3])
    # Actual execution comparison with clairvoyant prices only (NOT a bound on
    # an unknown global stochastic optimum): future demand/PV remain forecasts.
    oracle=np.full((365,4,144),np.nan)
    for v in range(4):oracle[:,v,:144-v*36]=data['actual_price'][:,v*36:]
    for mode in [2,3]:summaries.append(calc(mode,Policy() if mode==2 else pol,31,365,f'q4_{mode}_oracle',oracle,True)[3])
    dump_json(OUT/'summary.json',summaries)
    # Provable nominal-stage bound: identical 334 forecast feasible sets and
    # initial states for every price predictor, evaluated with true prices.
    states=pd.read_csv(OUT/f'q4_2_{selected["2"]}_daily.csv').soc_start_kwh.to_numpy()
    rr=cache[(2,.7,365)];regrets=[]
    for i,day in enumerate(range(31,365)):
        ptrue=data['actual_price'][day];L=ll[day,0]+rr[day,0];V=pv2[day,0]
        f,meta=solve(L,V,ptrue,states[i]);lower=float(ptrue@f.plan_kwh)
        for model in ['seasonal','ridge','gru_mean']:
            plan,_=solve(L,V,pp[model][day,0],states[i]);cost=float(ptrue@plan.plan_kwh)
            assert cost>=lower-1e-5
            regrets.append({'date':str(data['dates'][day].date()),'model':model,'nominal_cost':cost,'oracle_lower':lower,'regret':cost-lower})
    pd.DataFrame(regrets).to_csv(OUT/'nominal_price_bound.csv',index=False,float_format='%.17g')
    dump_json(OUT/'run_manifest.json',{'seconds':time.perf_counter()-beg,'input_audit':audit,
        'sources':{f:hashlib.sha256(Path(f).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for f in ['src/v3_model.py','src/v3_experiments.py']},
        'bound_scope':'fixed common nominal demand/PV forecasts, risk allowance, initial SOC and terminal constraints; no emergency execution claim'})
    print('COMPLETE',round(time.perf_counter()-beg,2),flush=True)

if __name__=='__main__':main()
