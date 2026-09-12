"""Continuous convex piecewise-linear storage values; no SOC discretization."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from src.q12 import B,audit_trace


@dataclass
class Value:
    x:np.ndarray
    y:np.ndarray
    def at(self,s):return np.interp(s,self.x,self.y)
    @property
    def slopes(self):return np.diff(self.y)/np.diff(self.x)


def restrict(f,lo=B.minimum,hi=B.maximum):
    lo=max(lo,float(f.x[0]));hi=min(hi,float(f.x[-1]))
    assert lo<=hi+1e-7
    x=np.unique(np.r_[lo,f.x[(f.x>lo+1e-8)&(f.x<hi-1e-8)],hi])
    y=f.at(x)
    if len(x)>2:
        slopes=np.diff(y)/np.diff(x);keep=np.r_[True,abs(np.diff(slopes))>1e-8,True]
        x,y=x[keep],y[keep]
    return Value(x,y)


def convolve(f,h):
    """Convex infimal convolution by merging segment slopes and lengths."""
    lengths=np.r_[np.diff(f.x),np.diff(h.x)];slopes=np.r_[f.slopes,h.slopes]
    order=np.argsort(slopes,kind='stable');lengths=lengths[order];slopes=slopes[order]
    x=np.r_[f.x[0]+h.x[0],f.x[0]+h.x[0]+np.cumsum(lengths)]
    y=np.r_[f.y[0]+h.y[0],f.y[0]+h.y[0]+np.cumsum(lengths*slopes)]
    return restrict(Value(x,y))


def purchase_stage(net,p):
    # v=s_before-s_after; negative v charges, positive v discharges.
    lo=-B.eta_c*B.limit;hi=B.limit/B.eta_d
    zero=net/B.eta_d if net>=0 else net*B.eta_c
    x=np.unique(np.r_[lo,hi,np.clip(0,lo,hi),np.clip(zero,lo,hi)])
    y=p*np.maximum(0,net+np.where(x>=0,-B.eta_d*x,-x/B.eta_c))
    return Value(x,y)


def deterministic(load,pv,price,initial=6000,terminal=6000):
    n=len(price);values=[None]*(n+1);values[n]=Value(np.array([float(terminal)]),np.array([0.]))
    stages=[purchase_stage(l-v,p) for l,v,p in zip(load,pv,price)]
    for t in range(n-1,-1,-1):values[t]=convolve(values[t+1],stages[t])
    s=float(initial);records=[]
    for t,h in enumerate(stages):
        future=values[t+1];lo=max(future.x[0],s-h.x[-1]);hi=min(future.x[-1],s-h.x[0])
        choices=np.unique(np.clip(np.r_[lo,hi,future.x,s-h.x],lo,hi))
        costs=future.at(choices)+h.at(s-choices);end=float(choices[np.argmin(costs)])
        c=max(0,(end-s)/B.eta_c);d=max(0,(s-end)*B.eta_d);g=max(0,load[t]-pv[t]+c-d);w=g+pv[t]+d-load[t]-c
        records.append([g,c,d,max(0,w),s,end,load[t],pv[t],0.,price[t]]);s=end
    f=pd.DataFrame(records,columns=['plan_kwh','charge_kwh','discharge_kwh','spill_kwh','soc_start_kwh','soc_end_kwh','load_kwh','pv_kwh','emergency_kwh','price'])
    audit_trace(f,initial=initial)
    assert abs(float(price@f.plan_kwh)-float(values[0].at(initial)))<1e-6
    return f,values


def recourse_values(net,price,terminal_rate):
    """A historical path's perfect-information value; used only as an approximation.

    Emergency supply serves deficits only; it cannot charge storage. Surplus
    charges greedily, which is optimal for these nonincreasing future values.
    """
    n=len(net);out=[None]*(n+1)
    out[n]=Value(np.array([B.minimum,6000.,B.maximum]),terminal_rate*np.array([4800.,0.,0.]))
    for t in range(n-1,-1,-1):
        if net[t]>0:
            top=min(float(net[t]),B.limit)/B.eta_d
            h=Value(np.array([0.,top]),5*price[t]*np.array([net[t],net[t]-B.eta_d*top]))
            out[t]=convolve(out[t+1],h)
        else:
            a=min(-float(net[t]),B.limit)*B.eta_c;f=out[t+1]
            x=np.unique(np.r_[B.minimum,np.clip(f.x-a,B.minimum,B.maximum),B.maximum])
            out[t]=restrict(Value(x,f.at(np.minimum(B.maximum,x+a))))
    return out


def execute_value(plan,load,pv,initial,price,paths,terminal_rate):
    all_values=[recourse_values(net,price,terminal_rate) for net in paths]
    s=float(initial);rows=[]
    for t,(g,l,v,p) in enumerate(zip(plan,load,pv,price)):
        net=float(l-v-g);c=d=e=w=0.
        if net<=0:
            c=min(-net,B.limit,(B.maximum-s)/B.eta_c);w=-net-c;end=s+B.eta_c*c
        else:
            lo=max(B.minimum,s-min(net,B.limit)/B.eta_d);hi=s
            choices=np.unique(np.r_[lo,hi,*[f[t+1].x[(f[t+1].x>lo)&(f[t+1].x<hi)] for f in all_values]])
            costs=5*p*(net-B.eta_d*(s-choices))+np.mean([f[t+1].at(choices) for f in all_values],axis=0)
            end=float(choices[np.argmin(costs)]);d=B.eta_d*(s-end);e=max(0,net-d)
        rows.append([g,l,v,c,d,e,w,s,end,p]);s=end
    f=pd.DataFrame(rows,columns=['plan_kwh','load_kwh','pv_kwh','charge_kwh','discharge_kwh','emergency_kwh','spill_kwh','soc_start_kwh','soc_end_kwh','price'])
    audit_trace(f,initial=initial);return f
