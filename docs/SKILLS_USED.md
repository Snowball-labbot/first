# 本轮 skills 来源与使用范围

## 手册来源与安装

读取了本机 `share/数模C题作战手册.html` 的 GitHub 资源部分，以及 `share/赛前答疑_Python选题Agent分工与时间.html` 的协作建议。手册中的 star 数、获奖描述和通用题型示例未当作本题事实。

安装 `XiaoMaColtAI/math-modeling-skill`，固定来源版本 `3527fad922660397834a6167fc2b4c29ee64ba17`。安装使用 Codex 的 skill-installer：

```text
python <skill-installer>/scripts/install-skill-from-github.py --repo XiaoMaColtAI/math-modeling-skill --path . --name math-modeling --ref 3527fad922660397834a6167fc2b4c29ee64ba17
```

本机安装目录 `C:/Users/wu135/.codex/skills/math-modeling`，项目目录 `D:/国赛数学建模/first`。根目录 `使用指南.md` 为该 skill 的指南副本。没有运行仓库中的一键代理或不明远程安装脚本。

## 实际读取和使用

读取根 SKILL、使用指南、建模手、编程手、论文手的入口及相关自检清单，Excel、DOCX、科研可视化入口和交付协议。使用环境检查脚本；基础图调用 `export_figure.py` 与 `visual_qa.audit_layout`；模型采用本项目自行实现的 SciPy 和 NumPy 代码。Excel 使用本地 Codex Spreadsheets skill 的 Artifact Tool 模板导入／导出路径。

理论及接口引用核对了 SciPy MILP 与 scikit-learn Ridge 官方文档。没有检索本届 C 题外部解答，也没有借用其他参赛队的模型结果。

## 用户要求优先的适配

- 用户明确禁止 subagent，因此没有执行 skill 默认的独立 subagent 验收，也不会将作者自检描述为独立评审通过。
- 用户当前只要求第一二问初稿，并接受把正式图表制作交接给另一 Agent。故本轮提供 Markdown 初稿及四幅基础图，不执行全篇论文默认的八图／九候选图数量要求，也不声称完成全部四问或正式排版。
- 延续此前用户指定的 GitHub Markdown 协作方式，Word/PDF 为后续定稿事项。
- 输入时间、效率和费用解释按照本题与共同约定建立，未照搬手册或 skill 的通用算法示例。

本轮质量状态以实际测试、保存文件复算、图表检查和交接记录为准。不存在 M1/P1/P2/W1/W2 的独立 PASS 回执。
