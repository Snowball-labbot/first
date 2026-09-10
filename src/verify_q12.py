"""Read-only cross-check of exported workbooks against full precision traces."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from PIL import Image
from src.q12 import audit_trace, dump_json, interval_label


def close(actual, expected):
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-5)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def storage_values(frame):
    return np.array([[frame.iloc[i:i+24].charge_kwh.sum(),
                      frame.iloc[i:i+24].discharge_kwh.sum()] for i in range(0,144,24)])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-root',type=Path)
    args=parser.parse_args()
    out=Path('artifacts/q12')
    manifest=json.loads((out/'run_manifest.json').read_text(encoding='utf-8'))
    delivery=json.loads((out/'delivery_manifest.json').read_text(encoding='utf-8'))
    assert sha('src/q12.py')==manifest['source_sha256'], 'Model source changed since run'
    assert sha('src/deliver_q12.py')==delivery['builder_sha256'], 'Delivery builder changed'
    input_status='not checked; pass --data-root to verify original files'
    if args.data_root:
        for item in manifest['input_files']:
            assert sha(args.data_root/item['path'])==item['sha256'],item['path']
        input_status='all three input fingerprints match'
    summary=json.loads((out/'q2_summary.json').read_text(encoding='utf-8'))
    physical={}
    dates=pd.date_range('2025-02-01','2025-12-31').strftime('%Y-%m-%d').tolist()
    selected=None
    for strategy in summary['strategies']:
        trace=pd.read_csv(out/(strategy['strategy']+'_intervals.csv.gz'))
        assert trace.groupby('date').size().to_dict()==dict.fromkeys(dates,144)
        stamps=pd.to_datetime(trace.interval_start)
        assert stamps.tolist()==pd.date_range('2025-02-01',periods=334*144,freq='10min').tolist()
        physical[strategy['strategy']]=audit_trace(trace,initial=manifest['evaluation_initial_soc'])
        close(float(((trace.plan_kwh+5*trace.emergency_kwh)*trace.price).sum()),strategy['total_cost_yuan'])
        if strategy['strategy']==summary['selected_strategy']: selected=trace
    assert selected is not None
    q1=pd.read_csv(out/'q1_intervals.csv')
    physical['q1']=audit_trace(q1,initial=6000)
    close(q1.soc_end_kwh.iloc[-1],6000)
    q1_summary=json.loads((out/'q1_summary.json').read_text(encoding='utf-8'))
    close(float((q1.plan_kwh*q1.price).sum()),q1_summary['cost'])

    workbook_audit={}
    for n in (1,2):
        wb=load_workbook(out/f'result{n}.xlsx',read_only=True,data_only=False)
        assert wb.sheetnames==(['计划购电量','充放电量'] if n==1 else ['计划购电量','充放电量','紧急购电量'])
        for ws in wb:
            for row in ws:
                assert all(cell.data_type not in ('e','f') for cell in row),f'{ws.title}: unexpected formula/error'
        plan=wb['计划购电量']; storage=wb['充放电量']
        if n==1:
            rows=list(plan.iter_rows(min_row=2,max_col=2,values_only=True))
            assert len(rows)==144
            assert [r[0] for r in rows]==[interval_label(i) for i in range(144)]
            close([r[1] for r in rows],q1.plan_kwh)
            sr=list(storage.iter_rows(min_row=2,max_row=7,max_col=5,values_only=True))
            close([r[1:3] for r in sr],storage_values(q1))
            assert [r[0] for r in sr]==[f'{h:02d}:00-{h+4:02d}:00' for h in range(0,24,4)]
            assert [sr[0][3],sr[1][3]]==['00:00','24:00']
            close([sr[0][4],sr[1][4]],[6000,6000])
        else:
            rows=list(plan.iter_rows(values_only=True))
            assert len(rows)==335 and len(rows[0])==147
            assert list(rows[0][1:145])==[interval_label(i) for i in range(144)]
            assert [r[0].strftime('%Y-%m-%d') for r in rows[1:]]==dates
            close([r[1:145] for r in rows[1:]],selected.plan_kwh.to_numpy().reshape(334,144))
            close([r[145] for r in rows[1:]],selected.groupby('date').plan_kwh.sum())
            costs=((selected.plan_kwh+5*selected.emergency_kwh)*selected.price).groupby(selected.date).sum()
            close([r[146] for r in rows[1:]],costs)
            sr=list(storage.iter_rows(min_row=2,max_col=6,values_only=True))
            assert len(sr)==334*6
            for i,(date,g) in enumerate(selected.groupby('date',sort=True)):
                block=sr[6*i:6*i+6]
                assert block[0][0].strftime('%Y-%m-%d')==date
                assert all(r[0] is None for r in block[1:])
                assert [r[1] for r in block]==[f'{h:02d}:00-{h+4:02d}:00' for h in range(0,24,4)]
                close([r[2:4] for r in block],storage_values(g))
                assert [block[0][4],block[1][4]]==['00:00','24:00']
                close([block[0][5],block[1][5]],[g.soc_start_kwh.iloc[0],g.soc_end_kwh.iloc[-1]])
            # Expand exported contiguous events back to original slots. Check boundaries,
            # duplicate coverage, event quantities, and days with explicitly zero events.
            coverage={d:np.zeros(144,dtype=bool) for d in dates}
            seen_dates=set();current=None
            for row in wb['紧急购电量'].iter_rows(min_row=2,max_col=3,values_only=True):
                date,label,energy=row
                if date is not None:current=date.strftime('%Y-%m-%d')
                assert current in coverage
                seen_dates.add(current)
                actual=selected.loc[selected.date==current,'emergency_kwh'].to_numpy()
                if label=='无紧急购电':
                    close(energy,0);close(actual,0);continue
                start,end=label.split('-')
                slot=lambda s:(int(s[:2])*60+int(s[3:]))//10
                a,b=slot(start),slot(end)
                assert 0<=a<b<=144 and not coverage[current][a:b].any()
                assert np.all(actual[a:b]>1e-5)
                close(energy,actual[a:b].sum())
                coverage[current][a:b]=True
            assert seen_dates==set(dates)
            for date,covered in coverage.items():
                np.testing.assert_array_equal(covered,selected.loc[selected.date==date,'emergency_kwh'].to_numpy()>1e-5)
        workbook_audit[f'result{n}.xlsx']={'pass':True,'sha256':sha(out/f'result{n}.xlsx'),'sheets':wb.sheetnames}
        wb.close()

    report=Path('reports/Q1_Q2初稿.md')
    body=report.read_text(encoding='utf-8')
    images=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',body)
    assert len(images)==4
    for target in images:
        with Image.open(report.parent/target) as img:
            assert min(img.size)>1000
            assert min(img.info.get('dpi',(0,0)))>=299.9
        assert (report.parent/target).with_suffix('.svg').is_file()
    assert [int(n) for n in re.findall(r'^表 (\d+) [^\n]+\n\n\|',body,re.M)]==list(range(1,18))
    assert f"{q1_summary['cost']:,.2f}" in body
    selected_metric=next(r for r in summary['strategies'] if r['strategy']==summary['selected_strategy'])
    assert f"{selected_metric['total_cost_yuan']/1e4:,.2f}" in body
    dump_json(out/'final_verification.json',{'pass':True,'inputs':input_status,'physical':physical,
              'workbooks':workbook_audit,'report':{'figures':4,'tables':17,'key_numbers_match':True},
              'verifier_sha256':sha(__file__)})
    print('PASS: 4 full-year traces, physical/accounting checks, both workbooks, 4 figures and 17 tables.')


if __name__=='__main__':main()
