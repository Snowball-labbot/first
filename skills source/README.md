# 数学建模 Skills 合集

本目录收集面向**数学建模竞赛（CUMCM 国赛 / MCM-ICM 美赛）的 AI Agent Skills**，
供其他 Agent 直接读取使用。

> 收集日期：2026-09-11
> 全部通过 `git clone --depth 1` 从 GitHub 原仓库镜像而来，保留原始结构（SKILL.md / assets / scripts）。
> **这些是第三方开源项目，不是本项目原创。** 使用时请遵守各自仓库的 LICENSE。

## 一、怎么用这些 Skills

绝大多数 skill 遵循同一约定：目录里有 `SKILL.md`（含 frontmatter 元数据），Agent 读取后按其中的工作流执行。

**方式 1：直接让 Agent 读**
告诉 Agent：「读取 `skills source/<目录名>/SKILL.md`，按其中的流程完成这道建模题」。

**方式 2：装进 Agent 的 skills 目录**
```bash
# Claude Code / 兼容 skills 约定的客户端
cp -r "skills source/<目录名>" ~/.claude/skills/
# Codex
cp -r "skills source/<目录名>" ~/.codex/skills/
```

**方式 3：npx 安装（部分仓库支持）**
```bash
npx skills add <owner>/<repo> --all
```

## 二、AI Skills / Agent 类

| 目录 | 原仓库 | 用途与特点 |
|---|---|---|
| `MathModelAgent` | jihe520/MathModelAgent | 端到端全自动：读题→建模→编码→绘图→论文排版。内置 17 套 Typst 模板（国赛/美赛/华数杯等自动匹配）、建模知识库、9 步自动验收。**有桌面版**（Releases 下载，内置 Claude Code） |
| `XiaoMaColtAI-math-modeling-skill` | XiaoMaColtAI/math-modeling-skill | **三阶段工作流**（建模手→编程手→论文手）+ 五道质量门禁（M1/P1/P2/W1/W2），支持 Python/MATLAB 双语言，默认产出 Word 论文。含七类算法资料、出版级可视化规范、OpenAlex 文献检索 |
| `zhnnky329-MathModeling-skills` | zhnnky329/MathModeling-skills | 分阶段建模流程，代码分支支持 Python / MATLAB / **北太天元**（国产 MATLAB 替代） |
| `Lupynow-math-modeling-skills` | Lupynow/math-modeling-skills | 覆盖国赛 CUMCM（A/B/C）与美赛 MCM/ICM（A–F）**全部题型**的一条龙工具链 |
| `handsomeZR-mathmodel-skill` | handsomeZR-netizen/mathmodel-skill | 三竞赛（CUMCM/MCM/电工杯），支持 Claude Code 与 Codex CLI。**全程问答式驱动**，关键决策会先向你确认，适合保留人工掌控 |
| `xuec699-math-modeling-skills` | xuec699-sudo/math-modeling-skills | 工业级：双模式（全自动+人工把关）、6 维问题分流、**5 人评审团机制**、模型依赖 DAG |
| `BZD-math-modeling-skills` | BZDmathclub/bzd-math-modeling-skills | **论文智能评审**：用近五年国赛评阅细则、评分要点蒸馏而成，模拟真实评委给你的论文挑错打分。**封稿前必跑** |
| `mathodology` | sweetcornna/mathodology | 面向 MCM/ICM、CUMCM、华数杯、M3、HiMCM 的获奖级建模工作流 |
| `cumcm-c-problem-lfs` | liufanshan11/cumcm-c-problem-lfs | **只做国赛 C 题**的专用 skill（数据/统计类） |
| `cumcm-b-problem-lfs` | liufanshan11/cumcm-b-problem-lfs | 只做国赛 B 题的专用 skill（离散/优化类） |
| `cumcm-live-workflow-skill` | haoxilin/cumcm-live-workflow-skill | CUMCM 全流程实战：读题自查→建模出图→LaTeX→交叉审阅→填 result 模板→AI 自查表终审。含**去 AIGC 特征清单** |
| `capwitf-My-MathModeling-skills` | capwitf/My-MathModeling-skills | 证据链驱动，覆盖题面、复现、图表、审查与提交门禁 |
| `cumcm-paper-hand-skill` | Mr-potato-123/cumcm-paper-hand-skill | 面向 CUMCM 的**论文手**专用 skill（写作与排版） |
| `math-modeling-skill-pro` | skillforCUMCM/math-modeling-skill-pro | 139 篇案例卡 + 方法库 + 模板 + 代码骨架 + 自动验证工具 |
| `cumcm-math-modeling-codex-skill` | usst-yk/cumcm-math-modeling-codex-skill | 面向 Codex 的 CUMCM skill |
| `contest-route-selection` | y3519712124-ui/math-modeling-contest-route-selection | **选题与路线选择**专用（Codex/OpenAI skill）—— 对应"三人怎么定题"环节 |
| `Y-love-han-math-modeling-skill` | Y-love-han/math-modeling-skill | 证据优先运行时（mmflow），12 阶段状态机 P0–P11，逐阶段 fail-closed 门禁、哈希链账本可复现 |
| `xiaohudie-math-modeling` | logic1241/xiaohudie-math-modeling | 全自动求解（国赛/研赛/美赛）：六阶段流程 + 4 套 LaTeX 模板 + 16 个 Python 算法模板 + 论文质检 |

## 三、绘图 / 模板 / 资料类

| 目录 | 原仓库 | 用途 |
|---|---|---|
| `sci-box` | jihe520/sci-box | **科研图表 Skill**：SHAP / ROC / Taylor 图 / 云雨图 / 和弦图 / 环形热图等复刻模板（Python+Matplotlib，导出 PNG/PDF/SVG）+ draw.io 可编辑流程图模板（五层技术路线图等） |
| `CUMCMThesis` | latexstudio/CUMCMThesis | **国赛官方格式 LaTeX 论文模板**（已适配 2026 年格式） |
| `MathModelHub` | Juccy-12/MathModelHub | 美赛综合资源库：算法参考手册、LaTeX/Word 模板、可视化 Notebook（直方图/箱线图/热力图等）、美赛评审机制与五天时间轴 |
| `MCM-ICM_Study_Resources` | CQULeaf/MCM-ICM_Study_Resources | 真实队伍美赛备赛全记录（含三次模拟赛与正式赛完整论文、作者自评） |

## 四、针对 2026 C 题（微网电力调控）的推荐组合

| 阶段 | 推荐 skill | 理由 |
|---|---|---|
| 读题拆解 | `Lupynow-math-modeling-skills`、`contest-route-selection` | 题型识别与路线选择 |
| 主体建模求解 | `XiaoMaColtAI-math-modeling-skill`（三阶段+门禁，出 Word）或 `cumcm-c-problem-lfs`（C 题专用） | 规范化流程，减少遗漏 |
| 数据探索与出图 | `sci-box` + 本仓库 `插图配色/`（含 `mgstyle.py` 配色库与 `配色速查表.md`） | 图表是 C 题第一印象 |
| 论文排版 | `CUMCMThesis`（LaTeX）或 `XiaoMaColtAI` 的 Word 输出 | 符合国赛当届格式 |
| 封稿前评审 | `BZD-math-modeling-skills` | 用国赛评阅细则模拟打分，抓低级错误 |
| 全自动兜底 | `MathModelAgent` | 端到端跑通，可作为交叉验证的第二方案 |

## 五、注意事项

1. **AI 使用规范**：国赛 2026 有专门的《人工智能工具使用规定（试行）》，使用任何 AI skill 前先确认当届要求（是否需声明、是否限制范围），并保留使用记录。
2. **结果必须人工复核**：AI 最危险的失败模式是"数值极精确、推导极完整、但物理上不成立"。关键数字必须人工验算（例如单位、量纲、边界条件、与题面约束是否一致）。
3. **不要把 skill 输出直接当最终答案**。skill 提供的是流程与模板，建模假设、口径选择、结论判断仍须由人负责。
4. 部分仓库体量较大（如 `MathModelAgent` 含前端资源），若只为读流程，直接看其 `SKILL.md` 与 `README.md` 即可。
