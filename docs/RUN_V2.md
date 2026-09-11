# Version 2：模型修订、数据核算与复现

## 当前交付与结论

- [完整论文 V2（Word）](../reports/完整论文_V2.docx)；[可审阅 Markdown](../reports/完整论文_V2.md)。
- 五份结果文件：`artifacts/v2/result1.xlsx`、`result2.xlsx`、`result3.xlsx`、`result4-2.xlsx`、`result4-3.xlsx`。
- Q1原最优费用35126.948589元保持不变，新增自由弃电条件下LP与互斥MILP等价证明及显式循环消除。
- Q2保留原策略14132612.159246元；低终端候选费用反增10347.473022元且期末库存更少，未采用。
- Q3采用一月选出的q=0.5、β=0、12/18点更新，费用13765317.698262元，比V1降低323247.228406元（2.2944%）。
- Q4-2保留原岭回归日前方案14880535.049452元；新低终端候选未改善。
- Q4-3采用一月选出的同期价格预测与新滚动模型，费用14486341.421540元，比V1降低304160.000827元（2.0565%）。

两项滚动方案期末SOC与各自V1完全相同。保留方案与候选的选择是同一数据集上的研究修订，不声称V2交付组合有全新、未使用过的外部测试集。Q3 β=1消融虽然全年更低，因未获一月选择，未事后晋升为主结果。

## 可复现环境

本轮实际环境：Python 3.12.14、NumPy 2.3.5、SciPy 1.17.1、pandas 3.0.1、Matplotlib 3.10.9、CPU PyTorch 2.14.0。原仓库requirements的pandas版本为2.2.3；V2实际版本明确记录，不能当作旧环境逐位复刻。模型运行记录包含输入指纹、代码哈希、每次求解状态与耗时、实际选择规则。价格预测使用已保存的原始NPZ与39次训练日志，本轮未伪称重新训练GRU。

建议新建 `.venv-v2`，安装 `requirements-v2.txt`。模型复现不需要Word；文档重建另需Windows Word、pywin32、pypandoc-binary及本机math-modeling技能。技能使用项目推荐的固定版本；C题审阅入口为 `skills source/cumcm-c-problem-lfs/SKILL.md`。

在仓库根目录执行，`<DATA_ROOT>`目录包含`C题.pdf`与`附件/`：

```text
python -X utf8 -m unittest discover -s tests -v
python -X utf8 -m src.verify_q12 --data-root <DATA_ROOT>
python -X utf8 -m src.verify_q34 --data-root <DATA_ROOT>
python -X utf8 -m src.v2_experiments --data-root <DATA_ROOT>
python -X utf8 -m src.v2_verify --data-root <DATA_ROOT>
python -X utf8 -m src.v2_delivery --data-root <DATA_ROOT>
python -X utf8 -m src.v2_figures
python -X utf8 -m src.v2_report
python -X utf8 -m src.build_v2_word
python -X utf8 scripts/render_word.py reports/完整论文_V2.docx --out .qa/v2_paper/render --dpi 100
python -X utf8 -m src.v2_final_check
```

完整新实验本机运行约132秒，包含一月选择与12组全年回测，不含依赖安装、原GRU训练、文件导出和人工审阅。不要将其与不同机器的原稿耗时直接相除宣称加速比。单次LP/MILP比较见 `q1_comparison.json`；求解器更换导致原规则全年结果有数元级变化，不能把这种微差当作模型改进。

## 验证范围与材料目录

- `design_before_evaluation.json`：评价开始前写入的候选范围；`selection.json`：一月选择；`delivery_selection.json`：最终交付保留/修订规则。
- `verification.json`：新12组全年轨迹及Q1，逐槽物理平衡、版本恢复、原始观测与各费用分项独立复算。
- `paired_comparison.json`、`monthly_comparison.csv`：配对日与月度差额、期末存量、7/14/28日区块Bootstrap敏感性。
- `price_errors_by_issue.csv`：四个发布时刻分开的价格MAE/RMSE，重复目标不当作独立观测。
- `xlsx_audit.json`：两份新滚动工作簿424104个单元格读回比对，另三份保留原验证文件的逐字节副本。
- `specified_tables_manifest.json`：Q1单日与其余四类策略各四个指定日，共17套；每套完整6个购电槽、6个储能区块，非Q1另含紧急事件。
- 所有候选完整逐时、逐日、计划版本与每次求解状态均保存在`artifacts/v2/`。V1文件未覆盖。

## 已知边界

时标、效率、退款、波动价结算解释保留并需队内确认。仅本年度顺序回测；Bootstrap的区块可交换近似不能消除季节非平稳或模型修订选择偏差。新方案也不是严格随机动态最优控制。图表以模型诊断为主，新增3张均非柱图，沿用9张有数据支持的旧图；不在本轮扩张图表设计。

全部检查为单Agent作者复查，无独立subagent验收，遵循仓库单Agent约定。正文与支撑材料仍需队员核对后使用。本轮仅上传GitHub研究成果，不代为进行正式竞赛提交。

最终检查：17项测试通过，OOXML结构校验通过；V2 Word/PDF正文参考文献25页，含附录总页数以final_delivery_check.json为准。Poppler缺失，已用PyMuPDF渲染同一Word原生PDF。通用paper_format全文件检查对程序附录的Python注释#和解包符号**报Markdown误报，并将含附录总页数与30页正文上限比较；正文残留、图表连续编号、引用与实际正文页数由v2_final_check单独检查。首次发现的正文引用及表编号问题已修复。三张新版图及全篇分页总览已目视复查，最终编号修订后保留机器检查；仍需队员终审。额度读到剩余2%立即冻结并同步，未使用重置额度。
