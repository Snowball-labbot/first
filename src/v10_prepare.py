"""Aggregate verified full-period dispatch; no fitting, interpolation, or re-solving."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from scipy.io import savemat
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'artifacts/v10';out.mkdir(exist_ok=True)
 e=np.arange(0,2.001,.05);b=np.linspace(-5,5,41)
 data=dict(price_edges=e,power_edges=b,price_centers=(e[1:]+e[:-1])/2,power_centers=(b[1:]+b[:-1])/2)
 audit={}
 for key,filename in [('dayahead','q42_value_selected_intervals.csv.gz'),('rolling','q43_value_release_selected_intervals.csv.gz')]:
  path=ROOT/'artifacts/v5b'/filename;q=pd.read_csv(path)
  assert len(q)==334*144 and not q[['price','charge_kwh','discharge_kwh']].isna().any().any()
  signed=(q.charge_kwh-q.discharge_kwh)*6/1000
  assert signed.abs().max()<5+1e-8
  signed=signed.clip(-5,5)
  active=abs(signed)>1e-5 # 0.01 kW numerical-noise threshold
  hist,_,_=np.histogram2d(q.price[active],signed[active],bins=[e,b])
  assert hist.sum()==active.sum()
  data[key+'_density']=hist.T/hist.sum()*100
  data[key+'_active']=active.sum();data[key+'_n']=len(q);data[key+'_idle']=100*(~active).mean()
  audit[key]=dict(n=len(q),active=int(active.sum()),idle_percent=float(100*(~active).mean()),
   price_min=float(q.price.min()),price_max=float(q.price.max()),signed_min=float(signed.min()),signed_max=float(signed.max()),
   source=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
 savemat(out/'dispatch_distribution.mat',data)
 (out/'dispatch_distribution_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(audit,ensure_ascii=False))
if __name__=='__main__':main()
