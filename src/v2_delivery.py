"""Template-preserving V2 workbooks and complete requested-date tables."""
from pathlib import Path
import argparse,hashlib,json,shutil
import re
from copy import copy
from datetime import datetime
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.styles import Font,PatternFill,Alignment
from src.q12 import interval_label,dump_json
from src.deliver_q12 import blocks,emergency_runs


OUT=Path('artifacts/v2')
SOURCES={'1':'artifacts/q12/q1_intervals.csv','2':'artifacts/q12/ridge_q0.7_intervals.csv.gz',
    '3':'artifacts/v2/q3_v2_intervals.csv.gz','4-2':'artifacts/q34/q4_2_ridge_intervals.csv.gz',
    '4-3':'artifacts/v2/q4_3_seasonal_intervals.csv.gz'}


def load_trace(key):
    f=pd.read_csv(SOURCES[key])
    if 'original_plan_kwh' not in f:f['original_plan_kwh']=f.plan_kwh
    if 'total_cost_yuan' not in f:f['total_cost_yuan']=f.price*(f.plan_kwh+5*f.emergency_kwh)
    return f


def table(title,headers,rows):
    def fmt(x):return f'{x:,.2f}' if isinstance(x,(float,np.floating)) else str(x)
    return '对应结果见'+title.split(' ',2)[0]+' '+title.split(' ',2)[1]+'。\n\n'+title+'\n\n| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(map(fmt,r))+' |\n' for r in rows)+'\n'


def specified_tables():
    text=['## 附录 A 四问指定日期完整结果\n\n电量单位为kWh，费用单位为元。普通购电与紧急购电分列。滚动问题的指定时段和全天购电量指最终有效普通计划；午夜计划及每次更新完整保存在Excel中。所有表由实际轨迹自动生成。\n']
    manifest=[]
    for key in SOURCES:
        f=load_trace(key);dates=['单日'] if key=='1' else ['2025-03-20','2025-06-21','2025-09-23','2025-12-21']
        text.append(f'### A.{key} 问题{key}\n')
        for date in dates:
            g=f if key=='1' else f[f.date==date]
            rows=[]
            for slots in [[60,72,84],[96,108,120]]:
                row=[]
                for slot in slots:row.extend([interval_label(slot),float(g.plan_kwh.iloc[slot])])
                rows.append(row)
            rows.append(['全天购电量',float(g.plan_kwh.sum()),'全天购电费',float(g.total_cost_yuan.sum()),'—','—'])
            text.append(table(f'表 A-{key}-{date}-1 指定时段购电及全天费用',['时间段','购电量']*3,rows))
            b=blocks(g);rows=[[*b[i],*b[i+1]] for i in range(0,6,2)]
            rows.append(['00:00储电',float(g.soc_start_kwh.iloc[0]),'—','24:00储电',float(g.soc_end_kwh.iloc[-1]),'—'])
            text.append(table(f'表 A-{key}-{date}-2 储能运行',['时间段','充电量','放电量']*2,rows))
            if key!='1':text.append(table(f'表 A-{key}-{date}-3 紧急购电',['时段','电量'],emergency_runs(g) or [['无',0.]]))
            manifest.append({'question':key,'date':date,'slots':[60,72,84,96,108,120],'blocks':6,
                'emergency_events':len(emergency_runs(g)),'cost':float(g.total_cost_yuan.sum())})
    dump_json(OUT/'specified_tables_manifest.json',manifest)
    combined='\n'.join(text)
    labels=re.findall(r'^表 (A-\S+) ',combined,re.M)
    for i,label in enumerate(labels,16):combined=combined.replace('表 '+label,'表 '+str(i))
    return combined


def export(root):
    # Accepted revisions are a within-dataset engineering choice. Preserve both rejected candidates.
    accepted={'1':'V1 retained (same optimal cost)','2':'V1 retained: new terminal candidate deteriorated',
        '3':'January-selected q=.5, terminal=6000, mask=6, beta=0',
        '4-2':'V1 retained: new terminal candidate deteriorated','4-3':'January-selected rolling q=.5 with seasonal prices'}
    dump_json(OUT/'delivery_selection.json',{'sources':SOURCES,'decisions':accepted,
        'interpretation':'V2 release retains V1 where revision failed; release acceptance is not a new untouched test-set selection.'})
    audits={}
    for key in SOURCES:
        if key in ['1','2','4-2']:
            src=Path('artifacts/q12' if key in ['1','2'] else 'artifacts/q34')/f'result{key}.xlsx'
            shutil.copy2(src,OUT/src.name);audits[key]={'copied_verified_v1':True,'sha256':hashlib.sha256(src.read_bytes()).hexdigest()}
            continue
        wb=openpyxl.load_workbook(root/f'附件/附件5/result{key}.xlsx')
        f=load_trace(key);payload={};plans=[];adjusted=[];storage=[];emergency=[];costs=[]
        for date,g in f.groupby('date',sort=False):
            dt=datetime.strptime(date,'%Y-%m-%d')
            plans.append([dt,*g.original_plan_kwh.tolist(),float(g.original_plan_kwh.sum()),float(g.original_cost_yuan.sum())])
            adjusted.append([dt,*g.plan_kwh.tolist(),float(g.plan_kwh.sum()),float(g.total_cost_yuan.sum())])
            for i,b in enumerate(blocks(g)):
                storage.append([dt if i==0 else None,*b,'00:00' if i==0 else '24:00' if i==1 else None,
                    float(g.soc_start_kwh.iloc[0]) if i==0 else float(g.soc_end_kwh.iloc[-1]) if i==1 else None])
            for i,e in enumerate(emergency_runs(g) or [['无',0.]]):emergency.append([dt if i==0 else None,*e])
            costs.append([dt,*[float(g[c].sum()) for c in ['original_cost_yuan','increase_cost_yuan','decrease_cost_yuan','emergency_cost_yuan','total_cost_yuan']]])
        head=['日期',*[interval_label(i) for i in range(144)],'全天购电量','全天购电费']
        payload.update({'计划购电量':[head,*plans],'调整购电量':[head,*adjusted],
            '充放电量':[['日期','时间段','充电量','放电量','时刻','储电量'],*storage],
            '紧急购电量':[['日期','时间段','电量'],*emergency],
            '费用分解':[['日期','午夜计划费','增购费','减购净费用','紧急费','总费'],*costs]})
        vp=Path(SOURCES[key].replace('_intervals','_versions'));v=pd.read_csv(vp);vr=[]
        for (date,ver),g in v.groupby(['date','version'],sort=True):
            values=[None]*144
            for r in g.itertuples():values[int(r.slot)]=float(r.new_kwh)
            vr.append([datetime.strptime(date,'%Y-%m-%d'),f'{int(ver)*6:02d}:00',*values])
        payload['计划版本']=[['日期','发布时间',*head[1:145]],*vr]
        payload['口径说明']=[['事项','约定'],['版本',accepted[key]],['时间','按输入右端点解释为十分钟区间，输出标签00:00—24:00'],
            ['费用','午夜计划+逐次增购1.5倍-减购0.5倍+紧急5倍；按交付区间实际价'],
            ['调整购电量','最终有效普通计划，非调整差值；已执行区间在版本表留空'],['储能','母线侧电量，两侧效率各0.9，实际SOC跨日连续']]
        for title,rows in payload.items():
            ws=wb[title] if title in wb.sheetnames else wb.create_sheet(title)
            for row in ws:
                for cell in row:cell.value=None
            for i,row in enumerate(rows,1):
                for j,val in enumerate(row,1):
                    c=ws.cell(i,j,val)
                    if i==1:c.font=Font(name='Microsoft YaHei',bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='3E608D')
                    elif isinstance(val,datetime):c.number_format='yyyy-mm-dd'
                    elif isinstance(val,(int,float)):c.number_format='0.00'
            ws.freeze_panes='B2';ws.column_dimensions['A'].width=16;ws.column_dimensions['B'].width=22
        dest=OUT/f'result{key}.xlsx';wb.save(dest);wb.close()
        reread=openpyxl.load_workbook(dest,data_only=False);count=0
        for sheet,rows in payload.items():
            for i,row in enumerate(rows,1):
                for j,expected in enumerate(row,1):
                    actual=reread[sheet].cell(i,j).value
                    if isinstance(expected,(int,float)):
                        assert isinstance(actual,(int,float)) and np.isclose(actual,expected,atol=1e-7,rtol=1e-12)
                    else:assert actual==expected,(sheet,i,j,actual,expected)
                    count+=1
        assert not any(c.data_type=='e' for ws in reread for row in ws for c in row)
        reread.close();audits[key]={'cells_compared':count,'pass':True,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}
    dump_json(OUT/'xlsx_audit.json',audits);print('Five result workbooks verified', {k:v.get('cells_compared','V1 exact copy') for k,v in audits.items()})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);a=p.parse_args();export(a.data_root)
