"""Build a self-contained supporting archive, excluding original problem data."""
from pathlib import Path
import sys
import json
import shutil
import hashlib
import zipfile
import pandas as pd
from scipy.io import loadmat,savemat

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.v12_document import PROGRAMS
from src.v12_results import SOURCES,VERSIONS

def main():
    stage=ROOT/'.qa/v12/support'
    stage.mkdir(parents=True,exist_ok=True)
    paths=[*PROGRAMS,*SOURCES.values(),'artifacts/v5/online_selection.csv',
           'artifacts/v10/dispatch_distribution.mat']
    paths += [str(p.relative_to(ROOT)).replace('\\','/') for p in
              (ROOT/'results/V12/附件5').glob('result*.xlsx')]
    for name in paths:
        dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dest)
    for name in VERSIONS.values():
        dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True)
        f=pd.read_csv(ROOT/name)
        f[['date','version','effective_slot','slot','old_kwh','new_kwh']].to_csv(
            dest,index=False,float_format='%.17g',compression={'method':'gzip','compresslevel':9,'mtime':0})
    dest=stage/'artifacts/v8/figure_data.mat'
    savemat(dest,{k:v for k,v in loadmat(ROOT/'artifacts/v8/figure_data.mat').items()
                 if not k.startswith('_')},do_compression=True)
    (stage/'requirements.txt').write_text('numpy\npandas\nscipy\nopenpyxl\n',encoding='utf8')
    readme='''# V12 支撑材料

五份填写完成的 Result 位于 results/V12/附件5。仅含原模板工作表，按当天零点起的144个十分钟区间填写；计算精度保存在单元格中，显示保留两位小数。

压缩包不含题目原始附件。安装 Python 3.12 和 requirements.txt 中的依赖后，在解压根目录运行以下命令（路径替换为本地题目附件位置）。

~~~text
python -m pip install -r requirements.txt
python -m src.v12_results --templates "<C题目录>/附件/附件5"
python -m src.v12_reproduce --data-root "<C题目录>" --days 1
python -m src.v12_reproduce --data-root "<C题目录>"
~~~

第一个运行命令填写并核验已保存的完整结果；第二个复算每个分支的首日，用于快速核验；第三个重新计算全部334天已选定策略，运行时间较长。复算使用冻结的历史月度选择中间结果，不重新开展参数搜索。原始题目文件只读。实际费用按最终合同量和真实交易价格重新核算；普通合同、取消、新增、紧急补购分别计费。

图形数值输入保存在 artifacts/v8/figure_data.mat 与 artifacts/v10/dispatch_distribution.mat。MATLAB R2026a 中：

~~~matlab
addpath('scripts');
v10_figures(pwd,fullfile(pwd,'support','V12'));
~~~

12张图沿用论文已经核验的MATLAB版本；图名中的v10表示图形来源，文稿版本为V12。重新汇总价格—储能功率分布可先执行 python -m src.v10_prepare。

artifacts/v5b 中的 selected_intervals 文件保留全部执行轨迹；versions 文件保留日期、发布时间版本、有效起点、目标区间、修改前后计划，未重复打包可由原始附件与程序生成的预测输入列。文件散列和长度见 MANIFEST.json。
'''
    (stage/'README.md').write_text(readme,encoding='utf8')
    manifest={str(p.relative_to(stage)).replace('\\','/'):
        {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in stage.rglob('*') if p.is_file() and p.name!='MANIFEST.json'}
    (stage/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    archive=ROOT/'results/V12/支撑材料_V12.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(stage.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(stage))
    assert archive.stat().st_size<20_000_000,archive.stat().st_size
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,item in manifest.items():
            assert hashlib.sha256(z.read(name)).hexdigest()==item['sha256']
    audit={'status':'PASS','bytes':archive.stat().st_size,'files':len(manifest)+1,
        'original_problem_attachments_included':False,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    (ROOT/'artifacts/v12/support_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
    print(audit)

if __name__=='__main__':main()
