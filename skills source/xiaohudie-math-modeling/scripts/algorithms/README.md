# Python 算法模板库

本算法库为本技能原创编写（社区同类仓库普遍缺少可执行的 Python 算法资产，本库补上这一缺口）。每个文件可独立运行（`python <文件>` 自测），可单独复制到 `求解/` 目录使用，也可 import 函数。用法与防错要点详见各文件 docstring 与 `references/model-selection.md`。

## 索引

| 文件 | 方法 | 适用场景 |
|---|---|---|
| evaluation/ahp.py | 层次分析法 AHP | 主观赋权（专家经验/层次结构），自动 CR 一致性检验 |
| evaluation/entropy_topsis.py | 熵权法 + TOPSIS | 客观赋权 + 多方案排序（评价类最常用组合） |
| evaluation/fuzzy_eval.py | 模糊综合评价 | 指标含模糊语言（好/中/差），M(·,+) 算子 |
| evaluation/grey_relation.py | 灰色关联分析 | 小样本因素强弱分析 |
| evaluation/critic.py | CRITIC 赋权 | 兼顾对比强度与冲突性的客观权重 |
| prediction/gm11.py | GM(1,1) 灰色预测 | 4~15 个数据点的短期指数趋势预测，含级比检验 |
| prediction/arima_forecast.py | ARIMA + ADF | 单变量时序（50+ 点），自动定阶、置信区间 |
| prediction/regression_eval.py | OLS/岭回归 + VIF | 多因素回归与诊断（共线性告警、残差检验） |
| prediction/exp_smoothing.py | 一次/Holt/Holt-Winters | 少样本中短期预测（纯 numpy，含季节项） |
| optimization/lp_nlp.py | scipy LP/NLP | 线性/非线性规划，含最大化取负、约束回代校验、物理约束演示 |
| optimization/genetic_algorithm.py | 实数编码 GA | 非凸/黑箱连续优化（SBX 交叉+精英保留） |
| optimization/sa_tsp.py | 模拟退火 + TSP | 组合优化/路径规划（含 Hamilton 回路验证） |
| optimization/pso_demo.py | 粒子群 PSO | 连续优化（Clerc 参数），含多次运行稳定性检查 |
| classification/ml_pipeline.py | sklearn 分类流水线 | 有标签分类：双模型对比+交叉验证+混淆矩阵+F1/AUC |
| graph/shortest_path.py | Dijkstra + Floyd | 最短路（负权保护、路径还原） |
| graph/max_flow.py | Edmonds-Karp 最大流 | 网络流/最小割（流量守恒验证） |

## 使用约定

1. **先看 references/model-selection.md 选型，再拿对应文件改造**；不要拿着锤子找钉子。
2. 求解脚本开头统一 `from common import *`（见 references/python-standards.md）。
3. 随机算法（GA/SA/PSO）报告结果时必须附：种子、运行次数、均值±标准差。
4. 所有结果落 `结果/`、图落 `图片/`，论文只引用落盘数值。
