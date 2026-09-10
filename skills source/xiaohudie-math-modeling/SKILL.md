---
name: math-modeling
description: 数学建模竞赛全自动求解技能（国赛CUMCM/美赛MCM-ICM/研赛华为杯GMCM/MathorCup等）。当用户提到数学建模、数模、建模竞赛、赛题求解、读题建模、写数模论文、摘要、模型建立、求解代码、灵敏度分析、TOPSIS、AHP、熵权法、灰色预测、遗传算法、优化/预测/评价/分类建模，或给出赛题PDF/数据附件要求完成论文时使用。覆盖从读题、建模、Python求解、LaTeX论文到编译质检的完整流程。
---

# 数学建模竞赛求解技能

由 xiaohudie 独立设计制作：六阶段求解流程、方法论参考文档、Python 算法模板库与国赛论文模板均为原创整理；少量直接引用的第三方文件及其许可状态见 SOURCES.md。

## 运行模式

- **默认（交互模式）**：两个关键节点暂停询问用户——① 拆题与建模方案确认；② 论文模板/排版引擎确认。其余自主推进。
- **全自动模式**：用户说"全自动/无人值守/直接跑完"时，全程不询问，所有决策点自行选择最优方案，一气呵成到编译通过。

## 第一步：环境自检

接手任务后先运行一次（产物路径随调用位置变化，脚本在技能目录 `scripts/` 下）：

```bash
python "<技能目录>/scripts/env_check.py"
```

按其输出行动：缺 Python 包给出安装命令；无 xelatex 时论文走 Markdown→docx 降级路径（见 references/latex-rules.md 末节），并告知用户。

## 项目目录结构（在用户工作目录创建）

```
.
├── 题目/                  # 用户放入赛题 PDF/DOCX
├── 数据/                  # 用户放入附件数据（xlsx/csv/docx）
├── 求解/                  # 自动生成
│   ├── 求解计划.md
│   ├── 预处理数据.csv     # 问题1产出，后续共用
│   ├── 问题一/问题一_<描述>.py + 图片/ + 结果/
│   └── 问题N/...
├── 论文/                  # 自动生成（LaTeX 或 Markdown）
└── 检查/                  # 质检报告 writing_check 报告、编译日志摘录
```

## 六阶段总流程

### 阶段 1：读题与数据体检
1. 读 `题目/`（PDF 用 PyPDF2/pymupdf，DOCX 用 python-docx），公式与上下标要二次核对。
2. 读 `数据/` 全量数据（不只前几行）：检查各 sheet 列数一致性、类型混入、合并单元格、多级表头、隐藏 sheet。
3. 打印数据总览（行×列、列名、类型、异常行）；识别问题数 N。
4. 读 references/model-selection.md 做"五大题型"判断（优化/预测/评价/分类聚类/机理），每个子问题明确输入、输出、决策变量、评价指标、约束。

### 阶段 2：求解计划
写 `求解/求解计划.md`（模板见 templates/plan-template.md），六章：题目总体方向、各题求解思路（含方法匹配表）、各题输出标准（图表规划）、操作步骤（含依赖）、文件清单、异常预案。
**交互模式在此节点向用户确认方案；全自动模式直接继续。**

### 阶段 3：逐问求解
1. 每问一个 py 文件（中文命名，放 `求解/问题X/`）。
2. **先算后画**：先完成全部计算，打印每组数据 min/max/mean/std/CV/amplitude（供论文引用），再画图（每问 4-6 张，覆盖主要分析维度）。
3. 问题1产出 `求解/预处理数据.csv` 供后续共用。
4. 灵敏度分析前置到本阶段：测关键参数 ±20% 扰动，记录结果供论文第6章引用。
5. 报错自修复重跑（≤3 次；仍失败则降级为更简单的模型，不换问题逻辑）。
6. 代码规范先读 references/python-standards.md；通用绘图/统计算法直接复用 `scripts/common.py` 与 `scripts/algorithms/`（每个算法可独立运行，含防错要点）。

### 阶段 4：论文撰写
1. 按竞赛选模板（交互模式先确认）：

| 竞赛 | 模板目录 | 语言 |
|---|---|---|
| 国赛 CUMCM | `templates/cumcm/`（含内嵌字体，跨机可编译） | 中文 |
| 研赛/华为杯 GMCM | `templates/gmcm/` | 中文 |
| 美赛 MCM/ICM | `templates/mcm/`（Summary Sheet 制） | 英文 |
| 其他赛事/通用 | `templates/default-zh/` | 中文 |

2. 把所选模板整目录复制到 `论文/`，按 N 动态增删问题章节。
3. 逐章写作规范读 references/paper-writing.md（摘要三种句式与字数配比、四类问题建模骨架、算法选择五段式、longtable 列宽通式、参考文献 GB/T 7714）。排版硬规则读 references/latex-rules.md。
4. **论文中所有数值必须来自求解阶段的真实输出**，禁止编造或重新估算。
5. 摘要最后写；美赛 Summary Sheet 独立一页（英文、含 AI 使用声明附录，25 页限制）。

### 阶段 5：编译与排版自修复
1. `xelatex -interaction=nonstopmode 论文.tex` 连跑两遍。
2. 运行 `python "<技能目录>/scripts/writing_check.py" <论文目录>` 做质检（Error 计数、Overfull/Underfull、乱码"？?"、占位符残留、图表引用存在性、cite/label 对应、摘要一页校验）。
3. FAIL 项定位修复后重编译，循环直到通过。

### 阶段 6：交付
输出 `检查/VERIFY_REPORT.md`（检查项、结果、遗留问题），向用户汇报：产物清单、核心结论、复现方式。合规提醒见 references/compliance.md。

## 参考文档路由表

| 时机 | 读 |
|---|---|
| 判断题型、选模型 | references/model-selection.md |
| 写各章节正文 | references/paper-writing.md |
| 写 LaTeX、编译、排版修复 | references/latex-rules.md |
| 写求解代码、画图 | references/python-standards.md |
| 整体节奏、时间管理、扣分点 | references/norms.md |
| AI 使用合规、学术诚信 | references/compliance.md |

## 硬规则速记（细节见对应参考文档）

1. 正一律自然段落，禁分点；`\textbf` 仅用于摘要"针对问题X"与问题重述"问题N："。
2. 图不画 set_title；图宽 0.8\textwidth；全图全表必须在正文被引用；图表文字与论文语言一致。
3. 所有表格统一 longtable + `>{\centering\arraybackslash}p{}`，列宽比例总和 = 1 − 0.03×列数（2 列=0.94、5 列=0.85）。
4. 章节之间不加 `\newpage`（参考文献、附录前的除外，模板已内置）。
5. 每问至少 4-6 张图；预测/分类必须含训练-验证划分；优化必须有约束可行性验证。
6. 参考文献只写真实存在的文献，每条被 \cite 引用。
7. 模型评价优点多于缺点（优点 4、缺点 2-3），按模型写不按问题写。
