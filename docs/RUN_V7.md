# V7 复现入口

从仓库根目录执行。原始附件位于上一级目录；替换 `--data-root` 可指定其他数据根目录，不修改原文件。

```powershell
.\.venv-v2\Scripts\python.exe -m src.v7_audit --data-root ..
.\.venv-v2\Scripts\python.exe -m src.v7_delivery
.\.venv-v2\Scripts\python.exe -m src.v7_trace_audit --data-root ..
.\.venv-v2\Scripts\python.exe -m unittest discover -s tests
.\.venv-v2\Scripts\python.exe -m src.v7_figures
.\.venv-v2\Scripts\python.exe src/v7_overview.py
.\.venv-v2\Scripts\python.exe -m src.v7_report
.\.venv-v2\Scripts\python.exe src/build_v7_word.py
.\.venv-v2\Scripts\python.exe src/v7_render.py
.\.venv-v2\Scripts\python.exe src/v7_final_check.py
```

后四问沿用 `artifacts/v5b/` 已发布最终轨迹，完整重新生成这些轨迹见 `V5_UPDATE_RUN.md`。原始数据及历史预测模型不是本轮重新拟合；本轮从原附件独立核对实际值、物理约束及账单。不得将历史轨迹复核说成重新训练。

Python依赖见项目既有环境；Word生成额外依赖Pandoc、python-docx和本机math-modeling文档工具，PDF由Windows Microsoft Word COM导出，渲染依赖PyMuPDF。`build_v7_word.py` 和 `v7_figures.py` 按当前用户主目录定位技能安装。源码输入及输出哈希保存在 `word_build.json` 和 `final_check.json`。

交付：`reports/完整论文_V7.docx`、PDF、Markdown与公式TeX；五份结果在 `artifacts/v7/`。`reports/V7正文源稿.md` 为带表格占位符的维护源，不作为阅读版。修改源稿后必须依次重建表格正文、Word、PDF和最终验收。
