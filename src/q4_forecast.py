"""Direct 24-hour price forecasts at four issue times, with monthly causal fits.

Seasonal, ridge and GRU see the same day/week lag curves and calendar. GRU
predicts a residual around the seasonal curve, not future observed prices.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import time
import numpy as np
import pandas as pd
import torch
from torch import nn
from src.q12 import ridge_fit, dump_json
from src.q34_data import read_extended

torch.set_num_threads(1)


def calendar(indices):
    hours=(indices%144+.5)/144
    dow=(indices//144+2)%7  # 2025-01-01 Wednesday
    return np.stack([np.sin(2*np.pi*hours),np.cos(2*np.pi*hours),
                     np.sin(2*np.pi*dow/7),np.cos(2*np.pi*dow/7)],axis=-1)


def features_at(flat,origin):
    assert origin>=1008
    target=np.arange(origin,origin+144)
    return np.column_stack([flat[target-144],flat[target-1008],calendar(target)]).astype('float32')


def ridge_features(x):
    a,b=x[...,0],x[...,1]
    context=np.stack([a.mean(-1),b.mean(-1),a.std(-1),b.std(-1)],axis=-1)
    context=np.broadcast_to(context[...,None,:],(*a.shape,4))
    return np.concatenate([x,np.stack([a-b,a*b],axis=-1),context],axis=-1)


class PriceGRU(nn.Module):
    def __init__(self):
        super().__init__();self.gru=nn.GRU(6,32,batch_first=True);self.head=nn.Linear(32,1)
        nn.init.zeros_(self.head.weight);nn.init.zeros_(self.head.bias)
    def forward(self,x):
        h,_=self.gru(x)
        return .5*(x[:,:,0]+x[:,:,1])+self.head(h).squeeze(-1)


def train_gru(x,y,origins,cutoff,seed,max_epochs=50):
    train=(origins+144<=cutoff-3*144);valid=(origins>=cutoff-3*144)
    assert train.sum()>0 and valid.sum()>0
    torch.manual_seed(seed);torch.use_deterministic_algorithms(True)
    mean=float(x[train,:,:2].mean());scale=max(float(x[train,:,:2].std()),1e-6)
    z=x.copy();z[:,:,:2]=(z[:,:,:2]-mean)/scale;target=(y-mean)/scale
    tx=torch.tensor(z[train]);ty=torch.tensor(target[train]);vx=torch.tensor(z[valid]);vy=torch.tensor(target[valid])
    model=PriceGRU();opt=torch.optim.Adam(model.parameters(),lr=.003)
    best=float('inf');weights=None;stale=0;history=[];rng=np.random.default_rng(seed)
    for epoch in range(max_epochs):
        model.train();order=rng.permutation(len(tx));losses=[]
        for left in range(0,len(order),32):
            idx=order[left:left+32];opt.zero_grad()
            loss=nn.functional.smooth_l1_loss(model(tx[idx]),ty[idx])
            loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step();losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():score=float((model(vx)-vy).abs().mean())*scale
        history.append({'epoch':epoch+1,'training_huber':float(np.mean(losses)),'inner_validation_mae':score})
        if score<best-1e-7:best=score;weights=copy.deepcopy(model.state_dict());stale=0
        else:stale+=1
        if stale>=6:break
    model.load_state_dict(weights);model.eval()
    return model,mean,scale,history,int(train.sum()),int(valid.sum())


def same_day_errors(pred,actual,start,stop):
    values=[]
    for day in range(start,stop):
        for v in range(4):values.extend(pred[day,v,:144-v*36]-actual[day,v*36:])
    a=np.asarray(values)
    return {'mae':float(np.abs(a).mean()),'rmse':float(np.sqrt(np.mean(a*a))), 'targets':len(a)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--data-root',required=True)
    p.add_argument('--out',type=Path,default=Path('artifacts/q34'));p.add_argument('--smoke',action='store_true')
    args=p.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True);(out/'models').mkdir(exist_ok=True)
    data,_=read_extended(args.data_root);flat=data['actual_price'].ravel();started=time.perf_counter()
    stop=38 if args.smoke else 365
    origins=np.arange(1008,len(flat)-143,36)
    x=np.stack([features_at(flat,t) for t in origins]);y=np.stack([flat[t:t+144] for t in origins]).astype('float32')
    # Fit on Jan 15/22 then each month boundary; never use targets ending after fit time.
    fit_days=[d for d in range(14,stop) if d in [14,21] or data['dates'][d].day==1]
    result={name:np.full((stop,4,144),np.nan,dtype='float64') for name in ['seasonal','ridge1','ridge10','ridge100','gru17','gru42','gru2026']}
    all_logs=[]
    for day in range(7,stop):
        for v in range(4):
            sample=features_at(flat,day*144+v*36)
            result['seasonal'][day,v]=sample[:,:2].mean(-1)
    for fi,day in enumerate(fit_days):
        cutoff=day*144;end=fit_days[fi+1] if fi+1<len(fit_days) else stop
        choose=(origins+144<=cutoff)&(origins>=max(1008,cutoff-60*144))
        xx=x[choose];yy=y[choose];oo=origins[choose]
        assert (oo+144<=cutoff).all()
        future_x=np.stack([features_at(flat,d*144+v*36) for d in range(day,end) for v in range(4)])
        for alpha in [1.,10.,100.]:
            a=ridge_features(xx).reshape(-1,12);b=yy.ravel()
            model=ridge_fit(a,b,alpha);mean,scale,coef,intercept=model
            forecasts=((ridge_features(future_x)-mean)/scale)@coef+intercept
            result[f'ridge{alpha:g}'][day:end]=np.maximum(forecasts.reshape(end-day,4,144),.001)
        for seed in [17,42,2026]:
            t=time.perf_counter();model,mean,scale,history,nt,nv=train_gru(xx,yy,oo,cutoff,seed+day,max_epochs=12 if args.smoke else 50)
            z=future_x.copy();z[:,:,:2]=(z[:,:,:2]-mean)/scale
            with torch.no_grad():values=model(torch.tensor(z)).numpy()*scale+mean
            result[f'gru{seed}'][day:end]=np.maximum(values.reshape(end-day,4,144),.001)
            checkpoint=out/'models'/f'gru{seed}_fit{day:03d}.pt'
            torch.save({'state_dict':model.state_dict(),'mean':mean,'scale':scale,'fit_day':day,'seed':seed,
                'training_last_target_exclusive':cutoff,'architecture':'GRU(6,32)+Linear(32,1)+seasonal residual'},checkpoint)
            log={'fit_day':day,'fit_date':str(data['dates'][day].date()),'seed':seed,'actual_rng_seed':seed+day,
                'training_windows':nt,'inner_validation_windows':nv,'last_target_exclusive':int((oo+144).max()),
                'seconds':time.perf_counter()-t,'history':history,'checkpoint':str(checkpoint)}
            all_logs.append(log)
            print(f'price GRU seed={seed} fit={day}: {len(history)} epochs, {log["seconds"]:.1f}s, best inner MAE={min(r["inner_validation_mae"] for r in history):.4f}',flush=True)
        np.savez_compressed(out/'price_forecasts_checkpoint.npz',**result)
        dump_json(out/'price_fit_log.json',all_logs)
    for name in result:
        if name!='seasonal':result[name][7:14]=result['seasonal'][7:14]
    result['gru_mean']=np.mean([result[f'gru{s}'] for s in [17,42,2026]],axis=0)
    validation={name:same_day_errors(values,data['actual_price'],21,31) for name,values in result.items()}
    ridge_name=min(['ridge1','ridge10','ridge100'],key=lambda n:validation[n]['mae'])
    result['ridge']=result[ridge_name]
    chosen=min(['seasonal','ridge','gru_mean'],key=lambda n:validation[ridge_name if n=='ridge' else n]['mae'])
    metrics={name:same_day_errors(result[name],data['actual_price'],31,stop) for name in ['seasonal','ridge','gru17','gru42','gru2026','gru_mean']}
    for name in ['seasonal','ridge','gru17','gru42','gru2026','gru_mean']:assert np.isfinite(result[name][21:]).all()
    np.savez_compressed(out/'price_forecasts.npz',**result)
    dump_json(out/'price_forecast_summary.json',{'validation':validation,'evaluation':metrics,'ridge_selected':ridge_name,
        'selected_by_validation_price_mae':chosen,'seeds':[17,42,2026],'torch_version':torch.__version__,
        'epochs_max':12 if args.smoke else 50,'fit_days':fit_days,'elapsed_seconds':time.perf_counter()-started,
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'evaluation_note':'Same-day suffix only, at each issue time; repeated targets at different origins counted separately.',
        'training_rule':'Whole 24h targets end before fit; last 3 days internal validation; refit monthly from scratch, last 60 days; Jan15/22 initialization.',
        'clip_floor':.001,'architecture':'Direct aligned day/week lag sequences plus known calendar; residual GRU(6,32), no future teacher forcing'})


if __name__=='__main__':main()
