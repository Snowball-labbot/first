# 冒烟测试样例

- `题目B：零售销售额的预测与数据分析.pdf` —— 示例赛题（来自 Mrite 仓库）
- `data.csv` —— 9800 行 × 18 列美国零售订单数据（Kaggle Superstore 型公开数据：Order Date / Ship Mode / Region / Category / Sales 等）

## 用途

做技能流程验证（冒烟测试）：复制两个文件到新目录的 `题目/` 与 `数据/` 下，让技能按六阶段流程跑一遍小规模求解，检查：读题→计划→逐问求解→论文框架→质检脚本是否顺畅衔接。

## 建议的快速验证（小规模，约 10 分钟）

1. 只取 data.csv 前 2000 行、只解"问题一"（销售额预测）。
2. 跑 `scripts/env_check.py` 确认环境。
3. 求解脚本引用 `scripts/common.py` 与 `algorithms/prediction/regression_eval.py`（或 `exp_smoothing.py`）。
4. 画 2 张图（趋势折线+相关性热力图，用 `assets/figures/` 模板）。
5. 按 cumcm 模板写 0.摘要 + 5.1 两章即可，不必成稿——目的是验证链路。
