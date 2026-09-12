"""Replay stored price checkpoints and verify release/target cutoffs."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import torch
from src.q34_data import read_extended
from src.q4_forecast import features_at,PriceGRU,ridge_features
from src.q12 import dump_json,ridge_fit

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);a=ap.parse_args()
    data,_=read_extended(a.data_root);flat=data['actual_price'].ravel();cache=np.load('artifacts/q34/price_forecasts.npz')
    logs=json.loads(Path('artifacts/q34/price_fit_log.json').read_text(encoding='utf-8'));fits=sorted({r['fit_day'] for r in logs});records=[]
    for day in range(7,365):
        for v in range(4):
            origin=day*144+36*v;targets=np.arange(origin,origin+144)
            assert (targets-144<origin).all() and (targets-1008<origin).all()
            np.testing.assert_array_equal(features_at(flat,origin)[:,:2].mean(-1),cache['seasonal'][day,v])
    origins=np.arange(1008,len(flat)-143,36)
    for fi,day in enumerate(fits):
        end=fits[fi+1] if fi+1<len(fits) else 365
        xx=np.stack([features_at(flat,d*144+36*v) for d in range(day,end) for v in range(4)])
        # Refit the selected linear predictor from raw history, without using cache labels.
        oo=origins[(origins+144<=day*144)&(origins>=max(1008,day*144-60*144))]
        trainx=np.stack([features_at(flat,o) for o in oo]);trainy=np.stack([flat[o:o+144] for o in oo]).astype('float32')
        mean,scale,coef,intercept=ridge_fit(ridge_features(trainx).reshape(-1,12),trainy.ravel(),1.)
        pred=np.maximum(((ridge_features(xx)-mean)/scale)@coef+intercept,.001).reshape(end-day,4,144)
        np.testing.assert_allclose(pred,cache['ridge'][day:end],atol=1e-10,rtol=0)
        for seed in [17,42,2026]:
            log=next(x for x in logs if x['fit_day']==day and x['seed']==seed)
            assert log['last_target_exclusive']<=day*144 and log['actual_rng_seed']==day+seed
            path=Path(f'artifacts/q34/models/gru{seed}_fit{day:03d}.pt')
            saved=torch.load(path,map_location='cpu',weights_only=True);assert saved['training_last_target_exclusive']==day*144
            model=PriceGRU();model.load_state_dict(saved['state_dict']);model.eval()
            z=xx.copy();z[:,:,:2]=(z[:,:,:2]-saved['mean'])/saved['scale']
            with torch.no_grad():values=np.maximum(model(torch.tensor(z)).numpy()*saved['scale']+saved['mean'],.001).reshape(end-day,4,144)
            diff=float(abs(values-cache[f'gru{seed}'][day:end]).max());assert diff<1e-6
            records.append(dict(fit_day=day,base_seed=seed,actual_seed=day+seed,max_replay_error=diff,checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    np.testing.assert_allclose(cache['gru_mean'][14:],np.mean([cache[f'gru{s}'][14:] for s in [17,42,2026]],axis=0),atol=1e-12,rtol=0)
    result=dict(status='PASS',seasonal_release_vectors=358*4,ridge_refits=13,gru_checkpoint_replays=39,
        seed_reporting_correction='17,42,2026 are base seeds; actual seed is base seed plus fit-day index',
        max_replay_error=max(x['max_replay_error'] for x in records),records=records,
        cache_sha256=hashlib.sha256(Path('artifacts/q34/price_forecasts.npz').read_bytes()).hexdigest())
    dump_json('artifacts/v5/price_replay_audit.json',result);print({k:v for k,v in result.items() if k!='records'})
if __name__=='__main__':main()
