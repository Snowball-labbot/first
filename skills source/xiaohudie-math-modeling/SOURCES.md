# 来源与第三方内容声明（SOURCES）

本项目由 **xiaohudie 独立设计制作**：全部方法论文档、Python 代码、工具脚本与国赛论文模板均为原创整理。制作过程中参考了若干社区开源项目的方法论，并对少量直接包含的第三方文件逐项标注如下。许可条款见 [LICENSE.md](LICENSE.md)（个人学习与竞赛免费，禁止商用，禁止闭源分发）。

## 一、原创内容（xiaohudie）

- `SKILL.md`、`README.md`、`LICENSE.md`、本文件
- `references/` 全部 6 份方法论文档（选型、写作、排版、代码规范、总纲、合规）
- `scripts/common.py`、`scripts/env_check.py`、`scripts/writing_check.py`
- `scripts/algorithms/` 全部 16 个算法模板（评价/预测/优化/分类/图论）
- `templates/cumcm/` 全部章节 tex（重写，统一社区版本的规范矛盾，实测校准列宽公式）与 `templates/plan-template.md`
- `assets/figures/` 全部绘图模板

## 二、参考项目（方法论思路来源，未直接搬运其文件）

| 项目 | 参考内容 |
|---|---|
| [Rzna-5559/Mrite](https://github.com/Rzna-5559/Mrite) | 智能体六阶段求解流程、论文写作方法论、编译排版自修复循环的思路 |
| [jihe520/MathModelAgent](https://github.com/jihe520/MathModelAgent) | 题型→算法决策树与高分组合思想、代码规范思想、论文质检脚本思想 |
| [zhanwen/MathModel](https://github.com/zhanwen/MathModel) | 竞赛经验与时间管理、评阅原则、AI 工具使用合规线索 |

## 三、直接包含的第三方文件（逐项标注，按对应许可分发）

| 文件 | 出处 | 许可状态 |
|---|---|---|
| `templates/gmcm/`（研赛·华为杯模板） | [MathModelAgent](https://github.com/jihe520/MathModelAgent) `skills/5writing/templates/zh/huaweibei-latex`（本仓库内已做字体自动检测修复） | 其自定义许可：个人免费、禁商用、禁闭源分发 |
| `templates/mcm/`（美赛英文模板） | MathModelAgent `skills/5writing/templates/en/mcm-latex`（已修复宏定义笔误） | 同上 |
| `templates/default-zh/`（中文通用模板） | MathModelAgent `skills/5writing/templates/zh/default-latex` | 同上 |
| `templates/cumcm/format.cls` | [Mrite](https://github.com/Rzna-5559/Mrite)（基于 MIT 许可的 [cumcmthesis](https://github.com/charlielin37/cumcmthesis) v2.6 改造；本仓库内已做跨平台字体回退修复） | 上游 cumcmthesis 为 MIT；Mrite 仓库无 LICENSE 文件、README 宣称 MIT |
| `templates/cumcm/fonts/*.otf` 思源宋体 | Adobe/Google [Source Han Serif](https://github.com/adobe-fonts/source-han-serif) | SIL Open Font License 1.1，可自由分发 |
| `assets/sample/data.csv` 与示例赛题 PDF | Mrite 仓库（数据为 Kaggle 公开数据集类型，赛题为公开竞赛题目） | 随其 MIT 声明；仅作演示用途 |

## 四、合规声明

1. 公开分发或修改再分发本项目时，必须保留本文件与 `LICENSE.md` 全文，并显著标注修改内容。
2. 使用第三节所列文件时，须同时遵守 MathModelAgent 的许可条款（禁商用、禁闭源分发）。
3. 参赛提交的 AI 工具使用声明要求见 [`references/compliance.md`](references/compliance.md)，以当年赛事官方规程为准。
