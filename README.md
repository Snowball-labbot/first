## 最新交付：V5（2026-09-12）

[完整论文 Word](reports/完整论文_V5.docx) · [PDF](reports/完整论文_V5.pdf) · [模型与数据核验](docs/V5_REVIEW.md) · [五份结果及审计记录](artifacts/v5)

V5新增按历史28天月度选择的负载修正，第三问节省86,848.84元，第四问滚动节省98,116.50元；初末SOC分别相同。截图所述功率/电量、供给富余、计划计费三项均已专项核验。图形保留基础对照，V6再作视觉优化。以下为历史版本介绍。

## 最新论文：Version 4

[Word](reports/完整论文_V4.docx) · [PDF](reports/完整论文_V4.pdf) · [Markdown](reports/完整论文_V4.md) · [修订与核验说明](docs/V4_REVIEW.md)

V4更新摘要、问题重述、逐题分析和全文语言，增加整体建模思路图。计算结果沿用已核验的V3，位于 `artifacts/v3/`。

# C 题建模方案与协作交接

**当前入口：V3。[Word](reports/完整论文_V3.docx)、[Markdown](reports/完整论文_V3.md)、[修改结果、验证及接力](docs/V3_REVIEW.md)。** 保留模板，修正第一问时间边界与第三四问结算，重跑全年结果，优化图文并给出GRU名义费用改进上界。以下V1/V2内容为历史记录。

**Version 2 最新入口（2026-09-11）：[V2论文](reports/完整论文_V2.docx)、[Markdown](reports/完整论文_V2.md)、[改进结果与复现](docs/RUN_V2.md)、[第一阶段核验](docs/V2_AUDIT.md)。** 新成果在 `artifacts/v2/`；下文保留原有协作内容。Q3与Q4滚动分别比V1减少32.32万元和30.42万元；Q2与Q4日前的新候选未改善，保留原方案。

题目：2026 全国大学生数学建模竞赛 C 题《微网与外部电网电力调控策略》。

**当前阶段：第一、二问初稿与实验已实现，第三、四问仍为方案。** 第一问已求解，第二问已进行四组 334 天顺序回测。本仓库保留原有 HTML 讲解页面，用于三人协作，以及更换账号、电脑或 Agent 后继续工作。

最新交付（2026-09-11）：[第一二问 Word 修订初稿](reports/Q1_Q2修订初稿.docx)、[对应 Markdown](reports/Q1_Q2修订稿.md)、[LaTeX 公式源](reports/Q1_Q2公式.tex)、[格式／算法／数据复查与重建说明](docs/WORD_REVIEW.md)。Word 共 18 页、22 个编号公式、8 图、16 表，仍为前两问初稿。

历史入口：[第一二问原初稿](reports/Q1_Q2初稿.md)、[运行与结果说明](docs/RUN_Q12.md)、[交给图表 Agent 的说明](docs/FIGURE_HANDOFF.md)。结果副本位于 [artifacts/q12](artifacts/q12/)，含 `result1.xlsx`、`result2.xlsx`、逐时记录、验证表和审计记录。

## 先读什么

1. [交接记录：当前状态、用户偏好和下一步](docs/HANDOFF.md)
2. [四问建模方案：预测与优化分别做什么](docs/MODELING_PLAN.md)
3. [数据、时间、费用及物理约束约定](docs/DATA_CONTRACT.md)
4. [实验设计：训练集、GRU 对照和耗时预算](docs/EXPERIMENT_PLAN.md)
5. [参考报告阅读笔记](docs/REFERENCE_REPORT.md)
6. [图表配色与论文图形规范](docs/VISUAL_STYLE.md)

Agent 还应首先遵循根目录 [AGENTS.md](AGENTS.md)。原有入口：[讲解首页](index.html)、[C 题作战手册](数模C题作战手册.html)。旧 HTML 是辅助材料；若与题面和最新约定冲突，应核对原题并记录修订。

## 已选定的研究方向

| 问题 | 预测部分 | 决策部分 | 需要交付什么 |
| --- | --- | --- | --- |
| 第一问 | 直接使用附件 1，不训练预测模型 | 确定性线性规划；为保证充放电互斥，采用混合整数线性规划（MILP） | 单日购电和储能计划，result1.xlsx |
| 第二问 | 同期预测作为基线，岭回归预测负载和光伏作为候选；必要时比较树模型 | 带风险余量的日前购电优化＋因果运行仿真 | 计划费用与五倍紧急购电费用的权衡，result2.xlsx |
| 第三问 | 延续负载预测；使用附件 3 已提供的分时发布光伏预报 | 考虑调整费用的日内滚动优化（MPC） | 新预报是否值得使用，result3.xlsx |
| 第四问 | **试验 GRU 电价预测**，与同期预测、岭回归对照；LSTM 为可选扩展 | 复用第二、三问的调度框架，接入波动电价 | 两类策略各自的预测模型对照，result4-2.xlsx、result4-3.xlsx |

注意：**线性规划不等于线性回归。** 回归预测未来数值；规划决定购电和充放电安排。GRU 是否保留为最终方法由验证结果决定，不预设它一定优于简单模型。

## 数据与复现状态

- 题面、原始 Excel、空白结果模板和参考 PDF **本次没有上传**；本次同步包括方案、代码、已计算结果、图表、初稿和协作资料。
- 数据结构、原文件名和本机查找位置见 [数据约定](docs/DATA_CONTRACT.md)，文件指纹见 [输入清单](docs/INPUT_MANIFEST.json)。另一个账号若使用同一台电脑，可直接定位原文件；换电脑时需要另行取得这些输入并核验指纹。
- 不要把模板中的示例数值或参考报告自述结果当成本题实验结果。
- 第一、二问的实测结果已保存；第三、四问以及 GRU 尚未运行。早期方案文件中“未执行”的表述属于方案编写时的历史状态，最新状态以交接记录和运行记录为准。

换账号后可以直接发送：

> 请读取 Snowball-labbot/first 仓库的 AGENTS.md、docs/HANDOFF.md 和 docs/MODELING_PLAN.md，接续 C 题建模工作。先核对当前状态与数据可用性，不要把方案当成已完成实验；本次是否执行模型以我的新指令为准。

## 四问完整初稿

[完整 Word](reports/完整论文.docx) · [完整 Markdown](reports/完整论文.md) · [复查与交接](docs/FULL_REVIEW.md)

[第三问 Excel](artifacts/q34/result3.xlsx) · [第四问日前 Excel](artifacts/q34/result4-2.xlsx) · [第四问滚动 Excel](artifacts/q34/result4-3.xlsx)

