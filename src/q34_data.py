"""Strict attachment 3/4 parsing and causal hourly forecast alignment."""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
import openpyxl
from src.q12 import read_inputs, time_minutes, dump_json


def read_extended(root, audit_path=None):
    root=Path(root);data,base_audit=read_inputs(root)
    wb=openpyxl.load_workbook(root/'附件/附件3.xlsx',read_only=True,data_only=True)
    rows=list(wb.active.values);wb.close()
    assert len(rows)==1461 and len(rows[0])==26
    assert list(rows[0][2:])==[f'预报{i}小时' for i in range(1,25)]
    hourly=np.empty((365,4,24)); filled=0
    for day in range(365):
        date=data['dates'][day]
        for version in range(4):
            row=rows[1+day*4+version]
            if version==0:
                assert pd.Timestamp(row[0])==date
            elif row[0] in (None,''):
                filled+=1
            else:assert pd.Timestamp(row[0])==date
            assert time_minutes(row[1])==version*360
            hourly[day,version]=np.asarray(row[2:],float)
    wb=openpyxl.load_workbook(root/'附件/附件4.xlsx',read_only=True,data_only=True)
    rows=list(wb.active.values);wb.close()
    assert len(rows)==366 and len(rows[0])==145
    assert [time_minutes(v) for v in rows[0][1:]]==list(range(10,1441,10))
    assert pd.DatetimeIndex([r[0] for r in rows[1:]]).equals(data['dates'])
    prices=np.asarray([r[1:] for r in rows[1:]],float)
    checks={}
    for name,values in [('hourly_pv_kw',hourly),('actual_price',prices)]:
        assert np.isfinite(values).all(),f'{name}: missing/nonfinite'
        assert (values>=0).all(),f'{name}: negative values need investigation'
        if name=='actual_price':assert (values>0).all()
        q1,q3=np.quantile(values,[.25,.75]);iqr=q3-q1
        checks[name]={'shape':list(values.shape),'count':values.size,'missing_nonfinite':0,
            'negative':0,'zero':int((values==0).sum()),'min':float(values.min()),'max':float(values.max()),
            'iqr_flags_retained':int(((values<q1-1.5*iqr)|(values>q3+1.5*iqr)).sum()),
            'deleted':0,'imputed_numeric':0,'winsorized':0,'smoothed_observations':0}
    # An hourly point is an instantaneous forecast. Integrate its piecewise-linear
    # curve exactly over 10-minute cells. At lead 0 use the newest completed PV
    # interval (causally known) as a boundary proxy; midnight Jan 1 uses zero.
    pv=np.full((365,4,144),np.nan)
    for day in range(365):
        for version in range(4):
            start=version*36
            anchor=(data['pv'][day,start-1]*6 if start else
                    data['pv'][day-1,-1]*6 if day else 0.0)
            vals=np.r_[anchor,hourly[day,version]]
            edges=np.arange(145-start)/6
            powers=np.interp(edges,np.arange(25),vals)
            pv[day,version,start:]=(powers[:-1]+powers[1:])/12
    data.update(hourly_pv=hourly,pv_issued=pv,actual_price=prices)
    audit={'pass':True,'checks':checks,'date_forward_fills_structural_only':filled,
        'dates':365,'unique_issues':1460,'issue_hours':[0,6,12,18],
        'forecast_horizons_hours':list(range(1,25)),
        'alignment':'Hourly lead endpoints; piecewise-linear integration over 10-minute cells; lead-zero anchor from last completed observed PV interval; only current-day suffix traded.',
        'input_files':base_audit['input_files']+[
            {'path':name,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()}
            for name in ['附件/附件3.xlsx','附件/附件4.xlsx']],
        'unusable_past_slots':'NaN intentionally marks targets before each issue; never supplied to a solver',
        'auditor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if audit_path:dump_json(audit_path,audit)
    return data,audit


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--data-root',required=True)
    p.add_argument('--out',default='artifacts/q34/input_audit.json');args=p.parse_args()
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    _,audit=read_extended(args.data_root,args.out)
    print(json.dumps(audit,ensure_ascii=False,indent=2))
