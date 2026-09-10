# xiaohudie-math-modeling

> 由 **xiaohudie** 独立设计制作的数学建模竞赛全自动求解 Agent Skill（ZCode / Claude Code 兼容）——把赛题 PDF + 数据丢给 AI 助手，自动走完 读题 → 建模 → Python 求解 → 论文撰写 → 编译质检 全流程。

一套面向 AI 编程助手的完整数模工程资产：方法论参考文档、算法模板库、四套赛事论文模板、论文质检门禁，开箱即用。

## 特性

- **六阶段全自动流程**：环境自检 → 读题与数据体检 → 求解计划 → 逐问求解（先算后画 + 灵敏度前置）→ 论文撰写 → 编译与排版自修复；支持"全自动无人值守"或关键节点人工确认两种模式
- **四套论文模板**：国赛 CUMCM（内嵌思源宋体，跨机可编译）/ 研赛·华为杯 GMCM / 美赛 MCM-ICM（英文 Summary Sheet）/ 中文通用；均已实测 `xelatex` 两遍编译 **0 Error、0 Overfull**
- **16 个 Python 算法模板**（评价/预测/优化/分类/图论），每个含防错要点与自测，`python xxx.py` 即验
- **论文质检脚本**：编译 Error、Overfull、占位符残留、图表引用存在性、`\cite`/`\bibitem` 对应、摘要一页校验，一键 PASS/FAIL
- **防扣分知识库**：优化变量物理约束红线、数据泄露防范、机理题 EDA 分流、评委视角四原则等，均写入决策文档
- **合规指引**：AI 工具使用声明、学术诚信红线（按 2025-2026 赛事规定整理）

## 快速开始

### 安装（二选一）

```bash
# ZCode（用户级，所有工作区可用）
git clone https://github.com/logic1241/xiaohudie-math-modeling.git "%USERPROFILE%\.zcode\skills\math-modeling"

# Claude Code
git clone https://github.com/logic1241/xiaohudie-math-modeling.git "%USERPROFILE%\.claude\skills\math-modeling"
```

Linux / macOS 把 `%USERPROFILE%` 换成 `~/`。技能发现机制自动生效，无需注册。

### 使用

1. 把赛题放进工作目录 `题目/`、附件数据放进 `数据/`
2. 对 AI 助手说：**"开始求解"**（默认在拆题与模板选择两处与你确认），或 **"全自动求解"**（无人值守一气呵成）
3. 产物：`求解/`（代码、图、结果）+ `论文/`（LaTeX 工程，可编译出 PDF）+ `检查/VERIFY_REPORT.md`

### 环境要求

```bash
python ~/.zcode/skills/math-modeling/scripts/env_check.py   # 一键自检并给出安装命令
```

必须项：Python 3.10+（numpy/pandas/matplotlib/scipy/scikit-learn）；论文出 PDF 需 XeLaTeX（MiKTeX/TeX Live），未安装时自动降级 Markdown→docx 路径。

## 目录结构

```text
math-modeling/
├── SKILL.md               # 技能入口：六阶段流程 + 参考文档路由
├── references/            # 按需加载的方法论（选型/写作/排版/代码/总纲/合规）
├── templates/
│   ├── cumcm/             # 国赛（format.cls + 14 章骨架 + 内嵌字体）
│   ├── gmcm/              # 研赛·华为杯
│   ├── mcm/               # 美赛英文
│   ├── default-zh/        # 其他中文赛事通用
│   └── plan-template.md   # 求解计划六章模板
├── scripts/
│   ├── common.py          # 求解公共头部（中文字体/学术配色/落盘工具）
│   ├── env_check.py       # 环境自检
│   ├── writing_check.py   # 论文质检门禁
│   └── algorithms/        # 16 个算法模板（evaluation/prediction/optimization/classification/graph）
├── assets/
│   ├── figures/           # 高级绘图模板（ROC+CI 置信带/雷达图/热力图/预测置信带）
│   └── sample/            # 冒烟测试样例（示例赛题 + 9800 行公开数据集）
├── SOURCES.md             # 来源署名与许可状态
└── LICENSE.md             # 自定义许可（个人/竞赛免费，禁商用，禁闭源分发）
```

## 独立制作内容

- **方法论体系**：references/ 全部 6 份文档（题型选型决策树、逐章写作规范、排版硬规则、代码规范、竞赛总纲、AI 合规指引）
- **Python 算法模板库**：16 个可独立运行自测的算法模板（评价/预测/优化/分类/图论，含熵权 TOPSIS、CRITIC 等社区仓库普遍缺失的评价方法）+ 求解公共头部、环境自检、论文质检三个工具脚本
- **国赛 CUMCM 模板**：14 章 LaTeX 骨架全部重写，统一了社区流传版本中的规范矛盾，实测校准了表格列宽公式（修正后 0 Overfull）
- **高级绘图模板与质检脚本**：ROC+置信带、雷达图、相关性热力图、预测置信带等 matplotlib 实现

## 参考与致谢

设计与方法论打磨过程中参考了以下社区开源项目，特此致谢；其中被直接引用的少量模板文件已在 [SOURCES.md](SOURCES.md) 中逐项标注出处与许可：

- [Mrite](https://github.com/Rzna-5559/Mrite) —— 智能体求解流程与论文写作方法论参考（国赛 format.cls 模板基于其 [cumcmthesis](https://github.com/charlielin37/cumcmthesis) 血统）
- [MathModelAgent](https://github.com/jihe520/MathModelAgent) —— 研赛/美赛/通用三套模板文件来源，题型决策与质检思想参考
- [zhanwen/MathModel](https://github.com/zhanwen/MathModel) —— 竞赛经验、评阅原则与 AI 合规线索参考

> 除上述标注文件外，本仓库其余内容均为原创。

## 许可

自定义许可：**个人学习与竞赛免费，禁止商用，禁止闭源分发**（与来源项目 MathModelAgent 的条款兼容），详见 [LICENSE.md](LICENSE.md)。参赛提交前请阅读 [compliance.md](references/compliance.md) 并核对当年赛事的 AI 使用规定。
