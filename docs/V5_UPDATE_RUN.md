# V5截图复核更新：交付与复现

最新论文仍为`reports/完整论文_V5.docx`、PDF、Markdown；最新五份工作簿在`artifacts/v5b/`。文件目录中的v5b表示V5本次增量，论文版本没有改为V6。图1—16保留基础模型对照，不代表新执行器的轨迹。

先读`V5_SCREENSHOT_COMPARISON.md`和`V5_SAVINGS_EXPLAINED.md`，最终自动检查见`artifacts/v5b/final_check.json`。本次主费用：Q1 35,126.85元；Q2 13,991,392.60元；Q3 13,479,283.32元；Q4日前14,765,492.68元、滚动14,210,881.01元。各全年分支均334天，不能相加。

## 执行约定

保留先前V5因果月度负载选择作为共同预测信号，新增历史路径库存价值控制。Q2用零终端价值；Q4日前使用当前可见真实电价、未来岭回归预测价；滚动分支在下次发布后用1.5倍预测价近似续期采购机会。紧急补购允许与保留部分库存同时发生，只服务当前负载，不能给电池充电。原即时平衡规则保留为基准，其“先尽量放电”测试仅检验旧执行器。

主策略按一月验证选定，滚动可调单候选是在一月固定合同价值失败后追加。所有策略、窗口试验属于同年数据的开发复核，没有未接触外部年度。84日训练窗、全年固定负载修正及Q2夜间终端价值的更低全年消融不作为事后回选依据。

## 运行顺序

在仓库根目录使用Python环境（numpy、pandas、scipy、openpyxl、python-docx、PyMuPDF、pypandoc、pywin32及既有PyTorch依赖）。原始附件目录放在参数`--data-root`下的`附件/`，以下用上一级目录举例。已完成的V3、V5预测和在线选择成果是此增量管线的输入；完整基线复现见先前V5文档。

```powershell
.venv-v2/Scripts/python.exe -m src.v5b_experiments --data-root ..
.venv-v2/Scripts/python.exe -m src.v5b_windows --data-root ..
.venv-v2/Scripts/python.exe -m src.v5b_rolling --data-root .. --case q3
.venv-v2/Scripts/python.exe -m src.v5b_rolling --data-root .. --case q42
.venv-v2/Scripts/python.exe -m src.v5b_rolling --data-root .. --case q43
.venv-v2/Scripts/python.exe -m src.v5b_analysis --data-root ..
.venv-v2/Scripts/python.exe -m src.v5b_delivery
.venv-v2/Scripts/python.exe -m unittest discover -s tests -v
.venv-v2/Scripts/python.exe -m src.v5b_report
.venv-v2/Scripts/python.exe -m src.build_v5b_word
.venv-v2/Scripts/python.exe -m src.v5b_render
.venv-v2/Scripts/python.exe -m src.v5b_final_check
```

Word构建使用本机已安装数模DOCX工具的Pandoc原生公式转换；PDF使用隐藏的Microsoft Word本机导出。基准论文快照在`artifacts/v5b/baseline_paper.md`，确保重建不把已经改过的V5反复叠加。

历史脚本`v5_report`、`build_v5_word`、`v5_render`、`v5_final_check`对应上一批V5输出，**不得在本次报告上直接运行旧的整套发布命令**，否则会还原旧正文/旧数值。旧`artifacts/v5/final_check.json`仅证明当时发布，不是本次文件的证书。

## 验证与后续

本次27项测试通过；11条全年轨迹529,056时段审计通过；24个新增滚动LP独立列式与对偶证书通过；Q1九个初始库存DP与MILP一致。四份更新工作簿649,041个数据单元格读回一致，Q1工作簿与已核验版相同。

论文保留45个既有原生公式对象，另有4个增量原生数学对象，共49个；37条编号显示公式、63张表、16幅原图。Word和PDF正文及参考文献27页（不含1页摘要），附录A从第29页起，总87页。全页已栅格化检查；公式、数据和模板检查独立于视觉检查。

V6可据新轨迹统一重绘流程及结果图，尤其不能将旧基础图只更改标题冒充新策略。建模后续优先考虑独立跨年数据、联合未来调单的场景树和跨日终端价值；没有在此次交付中实现的方向不作为已得结果。
