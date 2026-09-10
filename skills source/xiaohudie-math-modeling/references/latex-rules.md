# LaTeX 排版硬规则与编译自修复

> xiaohudie 独立整理的排版与质检规范（社区实践参考出处见 SOURCES.md）。国赛模板 templates/cumcm/ 已内嵌思源宋体（fonts/ 目录），跨机器可直接编译。

## 编译命令

```bash
cd 论文
xelatex -interaction=nonstopmode 论文.tex   # 连跑两遍解决目录与交叉引用
xelatex -interaction=nonstopmode 论文.tex
```

`grep -c 'Error' 论文.log` 必须为 0；有 Error 修复后重编译直到 0。

## 硬规则清单

1. **表格**：全论文所有表格统一 longtable + `>{\centering\arraybackslash}p{}` 样式（可跨页、自动重复表头），禁用 tabular/tabularx（附录附件表用 `>{\raggedright\arraybackslash}` 左列）。
2. **列宽通式**：各列比例总和 = 1 − 0.03 × 列数N（\tabcolsep 每列左右各 6pt，N 列共 12N pt；按标准版心 455pt 每列需预留约 3%）。**注意：网上流传的 1.04−0.04N 通式预留不足，N=2 时仍会溢出约 6pt**（本技能已实测校准）。

| 列数 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|
| 总和 | 0.94 | 0.91 | 0.88 | 0.85 | 0.82 | 0.79 | 0.76 | 0.73 | 0.70 |

3. longtable 固定结构：`\caption{}` → `\label{}` → `\\` → `\toprule` 表头 `\midrule` → `\endfirsthead`（续页重复表头）→ `\endhead` → `\endfoot`（含 `\bottomrule`）。缺 `>{\centering\arraybackslash}` 会报 `Misplaced \noalign`。
4. **图**：宽 `0.8\textwidth`；浮动体默认 `[htbp]`（9 框流程图模板用 `[ht]`）；图内禁止 `set_title`（标题由 `\caption{}` 承担）；图内只允许数据、坐标轴标签刻度、图例（与论文同语言）。
5. **全图全表必须被正文引用**（"如图X所示""如表X所示"），caption/标签中文化（国赛）。
6. **正文禁分点、禁 `\textbf`**（例外：摘要"针对问题X"、问题重述"问题N："、假设/评价的 itemize 标签）。
7. **禁 `\newpage`**：章与章、节与节之间一律不加，内容自然接续；仅参考文献与附录前允许（主文件已内置）。
8. 表格格子文字一行显示不换行。
9. 主文件用 `\documentclass[withoutpreface,bwprint]{format}`（cumcm 模板）；图片引用相对路径 `../求解/问题X/图片/xxx.png`。
10. 摘要必须 1 页（aux 中 `\label{abstract:end}` 页码校验）。

## 编译后自动排版优化循环

编译 0 错误后执行，直到日志干净：

1. `grep 'Overfull\|Underfull\|Float too large' 论文.log`（或直接运行 scripts/writing_check.py）。
2. 按 warning 定位对应 tex 文件与行。
3. 修复手段：缩短表格文字、按列宽通式调整 p{} 比例、缩小图宽、收紧段落。
4. `xelatex ×2` 重编译，重新检查。
5. 终止条件：无 Error、无 Overfull/Float too large、无大面积空白、图表正常。

## 文本质检门禁（writing_check.py 自动执行）

- 占位符残留：`...`、`TODO`、`PLACEHOLDER`、`待补充`、`【】`。
- 乱码：PDF 文本或日志中出现 `？？`。
- 图表引用：`\includegraphics` 的文件存在；每图有 `\caption`。
- 引用对应：每个 `\cite{}` 能对应 `\bibitem{}`，反之亦然。
- 摘要一页校验（aux 标签）。
- 编译产物非空、页数合理。

## 美赛（MCM/ICM）专项

- 论文总页数 ≤ **25 页**（含摘要、正文、参考文献、附录；AI 使用声明附录不计入）。
- Summary Sheet 独立一页（模板 templates/mcm/ 已内置 Team #、Page X of Y 页眉）。
- 允许使用 LLM/生成式 AI，但必须在附录中报告使用范围与校验方式。
- 图表尽量矢量（PDF）；获奖论文图表占比高，纯文字难获奖。

## 无 LaTeX 环境的降级路径

检测 `xelatex` 不存在时（env_check.py 会提示）：

1. 首选请用户安装 TeX 发行版：Windows `winget install MiKTeX.MiKTeX`（或 TeX Live；精简装 texlive-xetex + texlive-lang-chinese）。
2. 用户拒绝安装则降级：用 Markdown 写作（同一套章节结构与写作规范），图片用相对路径嵌入，最后 `pypandoc` 转 docx（参数 `markdown+tex_math_dollars --mathml --standalone`），明确告知格式与正式竞赛要求有差距、仅作草稿。
3. Typst 是轻量备选（`winget install Typst.Typst`），如用户指定则按其语法重排模板结构。
