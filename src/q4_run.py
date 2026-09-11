"""Compare each causal price forecast under both required dispatch policies."""
from pathlib import Path
import argparse,json,time,hashlib
import numpy as np
import pandas as pd
from src.q12 import forecasts,dump_json
from src.q34 import historical_buffers,backtest,save_run
from src.q34_data import read_extended


def main():
    p=argparse.ArgumentParser();p.add_argument('--data-root',required=True)
    p.add_argument('--out',type=Path,default=Path('artifacts/q34'));p.add_argument('--smoke',action='store_true');args=p.parse_args()
    out=args.out;data,_=read_extended(args.data_root);pred,_=forecasts(data,'ridge',(1.,1.))
    q3=json.loads((out/'q3_selection.json').read_text(encoding='utf-8'));buffers=historical_buffers(data,pred,q3['quantile'])
    prices=np.load(out/'price_forecasts.npz');names=['seasonal','ridge','gru17','gru42','gru2026','gru_mean']
    started=time.perf_counter();validation=[];selections={};summaries=[]
    for mode in [2,3]:
        for name in ['seasonal','ridge','gru_mean']:
            fit=backtest(data,pred,buffers,start=21,stop=31,initial=6244.256891388887,
                mask=q3['mask'] if mode==3 else 0,name=f'q4_{mode}_{name}',price_forecasts=prices[name],
                use_issued=mode==3,retain=False)
            validation.append({'mode':mode,'forecast':name,**fit[-1]})
        selections[str(mode)]=min([r for r in validation if r['mode']==mode],key=lambda r:r['total_cost_yuan'])['forecast']
    pd.DataFrame(validation).to_csv(out/'q4_validation.csv',index=False,float_format='%.17g')
    dump_json(out/'q4_selection.json',{'selected':selections,'basis':'January validation total realized cost separately by policy',
        'q3_mask':q3['mask'],'q3_quantile':q3['quantile'],'q2_quantile':.7})
    for mode in [2,3]:
        for name in names:
            label=f'q4_{mode}_{name}'
            result=backtest(data,pred,buffers,start=31,stop=38 if args.smoke else 365,initial=9902.811287870369,
                mask=q3['mask'] if mode==3 else 0,name=label,price_forecasts=prices[name],use_issued=mode==3)
            save_run(out,label,result);summaries.append({'mode':mode,'forecast':name,**result[-1]})
    dump_json(out/'q4_summary.json',summaries)
    dump_json(out/'q4_run_manifest.json',{'stage':'smoke' if args.smoke else 'full','seconds':time.perf_counter()-started,
        'source_sha256':{f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in ['src/q34.py','src/q34_data.py','src/q4_forecast.py','src/q4_run.py']}})


if __name__=='__main__':main()
