"""Monthly past-only validation of load correction, with continuous live SOC."""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
from src.q12 import dump_json,forecasts
from src.q34_data import read_extended
from src.v3_model import Policy,run,risk_buffers
from src.v5_model import adaptive_load

OUT=Path('artifacts/v5')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args()
    dump_json(OUT/'online_design_before_evaluation.json',{'update':'first day of every month','validation_days':28,
        'candidates':['baseline','adaptive'],'risk':.5,'terminal':6000,'mask':7,
        'selection':'common initial SOC from live state at start of historical validation window; realized historical costs; baseline wins ties',
        'february':'January selection, unchanged','price_model':'seasonal',
        'scope':'Predefined online selection extension; not an untouched external test'})
    data,_=read_extended(a.data_root);pred,_=forecasts(data,'ridge',(1.,1.));prices=np.load('artifacts/q34/price_forecasts.npz')['seasonal']
    loads={'baseline':np.repeat(pred['load'][:,None,:],4,axis=1),'adaptive':adaptive_load(data,pred['load'])[0]}
    buffers={k:risk_buffers(data,v,data['pv_issued'],.5) for k,v in loads.items()};policy=Policy(quantile=.5,mask=7)
    choices=[];summaries=[]
    for mode in [3,4]:
        state=9902.811287870369;states={31:state};pieces=[[],[],[],[]]
        for month in range(2,13):
            indices=np.flatnonzero(data['dates'].month==month);start=int(indices[0]);stop=int(indices[-1]+1)
            name='baseline'
            if month>2:
                left=start-28;vals=[]
                for candidate in ['baseline','adaptive']:
                    r=run(data,loads[candidate],data['pv_issued'],buffers[candidate],policy,start=left,stop=start,
                        initial=states[left],name='validation',prices=prices if mode==4 else None,retain=False)
                    vals.append(dict(mode=mode,month=month,candidate=candidate,validation_first_day=left,
                        validation_last_day=start-1,initial_soc=states[left],final_soc=r[3]['final_soc'],cost=r[3]['total_cost_yuan']))
                name=min(vals,key=lambda x:(x['cost'],x['candidate']!='baseline'))['candidate']
                choices.extend([{**v,'selected':v['candidate']==name} for v in vals])
            r=run(data,loads[name],data['pv_issued'],buffers[name],policy,start=start,stop=stop,initial=state,
                name=f'q{mode}_online',prices=prices if mode==4 else None,retain=True)
            state=r[3]['final_soc']
            for day,val in zip(range(start,stop),r[0].soc_start_kwh):states[day]=float(val)
            for dest,obj in zip(pieces,[r[0],r[1],r[2],r[4]]):dest.append(obj)
            print('online',mode,month,name,round(r[3]['total_cost_yuan'],2),flush=True)
        combined=[pd.concat(p,ignore_index=True) for p in pieces];daily=combined[0]
        for obj,suffix in zip(combined,['daily.csv','intervals.csv.gz','versions.csv.gz','solvers.csv.gz']):
            obj.to_csv(OUT/f'q{mode}_online_{suffix}',index=False,float_format='%.17g')
        from src.q12 import audit_trace
        summary=dict(strategy=f'q{mode}_online',days=334,initial_soc=9902.811287870369,final_soc=state,
            total_cost_yuan=float(daily.total_cost_yuan.sum()),emergency_kwh=float(daily.emergency_kwh.sum()),
            emergency_cost_yuan=float(daily.emergency_cost_yuan.sum()),physical=audit_trace(combined[1],initial=9902.811287870369))
        dump_json(OUT/f'q{mode}_online_summary.json',summary);summaries.append(summary)
    pd.DataFrame(choices).to_csv(OUT/'online_selection.csv',index=False,float_format='%.17g')
    dump_json(OUT/'online_summary.json',summaries)
if __name__=='__main__':main()
