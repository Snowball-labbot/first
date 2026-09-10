# 第一二问的运行与结果说明

## 1. 当前产物

- `reports/Q1_Q2初稿.md`：可在 GitHub 阅读的正文、公式、结果分析及指定日期表格。
- `src/q12.py`：数据检查、岭回归、风险余量、MILP、因果执行与物理审计。
- `src/deliver_q12.py`：从保存结果生成初稿、四幅基础图和 Excel 中间数据，不重新训练。
- `scripts/export_xlsx.mjs`：使用 Artifact Tool 读取原模板并另存 `result1.xlsx`、`result2.xlsx`。
- `artifacts/q12/`：逐时压缩 CSV、日指标、验证比较、效率敏感性、审计和结果副本。
- `figures/q12/`：四张图的 PNG 与 SVG。正式图表精修见 `FIGURE_HANDOFF.md`。

本轮新增的是第一二问初稿，第三四问和 GRU 没有实现。初稿使用 Markdown 延续此前 GitHub 协作方式；尚未生成排版定稿 Word/PDF。

## 2. 运行命令

在仓库根目录运行，Python 环境使用 `requirements.txt` 所列版本。本次用的是 Codex 提供的 Python 3.12.14；模型不需要 API Key 或 GPU。

```powershell
python -m unittest discover -s tests -v
python -m src.q12 --data-root "D:/国赛数学建模/CUMCM2026Problems/C题" --stage full --out artifacts/q12
python -m src.deliver_q12 --out artifacts/q12 --skill-root "C:/Users/你的账号/.codex/skills/math-modeling"
node scripts/export_xlsx.mjs "D:/国赛数学建模/CUMCM2026Problems/C题"
python -m src.verify_q12 --data-root "D:/国赛数学建模/CUMCM2026Problems/C题"
```

最后两个产物工具有额外依赖：绘图导出使用手册推荐并已安装的 `XiaoMaColtAI/math-modeling-skill`，版本固定为 `3527fad922660397834a6167fc2b4c29ee64ba17`；Excel 导出使用 Codex 的 `@oai/artifact-tool`。本机 `node_modules` 为指向 Codex 依赖目录的未提交 junction，换电脑需连接自己的运行时。若仅复现数学结果，前两条模型命令不依赖这两个工具。

Skill 安装命令和使用取舍见 `SKILLS_USED.md`。不要把本机绝对路径原样当作另一台电脑的配置。

## 3. 初始状态与模型选择

一月份统一热身从 6000 kWh 开始。1 月 1 日无历史时使用附件 1 曲线作为冷启动参考；随后不足七天采用近三日均值，之后使用日／周同期均值。该热身是假设明确的公共策略，费用不纳入题目要求的二月起评价。模型验证使用 1 月 22 日的共同热身状态；全年各组使用 2 月 1 日的同一状态。

正则强度按一月验证 MAE 选择，余量按一月验证总费用选择。全年比较固定四组：同期无余量、岭回归无余量、同期验证最优余量、岭回归验证最优余量。不得按二月至十二月结果继续挑参数后仍声称是完全未参与选择的测试。

每组实际 SOC 自行连续演化，日前名义终端下限 6000 kWh 不等于每天重置实际电量。日期、方法、价格和费用均保留在逐时／逐日文件中。

## 4. Excel 口径与模板差异

原模板时间标签疑似整体错位。结果副本将首区间改为 00:00—00:10、末区间改为 23:50—24:00，题面指定时刻按同一内部时间轴汇总。映射见 `time_mapping.csv`；正式提交前仍需队内核对这一解释。

result2 的“全天购电量”填普通计划量，紧急量在专门工作表记录；“全天购电费”填普通与紧急费用合计。若要所有外购电量，应将计划量与紧急量相加，不要把表头解释混用。

连续触发紧急购电的十分钟区间合并为一个事件，日期无紧急购电时记录“无紧急购电”和 0。充放电 sheet 覆盖 334 天的六个四小时区间，日初、日末 SOC 写在对应日的前两行。所有充放电量均为母线侧电量。

## 5. 已知局限

当前代码为确定性名义优化加风险余量和贪心实际控制，不能称为精确随机规划最优解；经验分位数不是联合供电可靠性保证。没有未来气象信息，光伏预测改善有限。一月份验证和固定终端目标的跨季节适用性仍需加强。

同源图、文字和表格均从结果重建。若改模型或费用口径，先运行模型，再更新正文与图表，不手工修改 CSV 或论文关键数值。`run_manifest.json` 记录运行时 Git HEAD 及实际 Python 源码指纹；由于运行早于本轮最终提交，应以源文件 SHA-256 核对本轮代码。
