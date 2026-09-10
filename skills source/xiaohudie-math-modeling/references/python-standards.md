# 求解代码规范

> xiaohudie 独立整理的求解代码规范（社区实践参考出处见 SOURCES.md）。可复用脚本：`scripts/common.py`（公共头部与工具函数）、`scripts/algorithms/`（算法模板库）。

## 依赖白名单

- 必装：pandas, numpy, matplotlib, scipy, scikit-learn, chardet, openpyxl
- 禁用绘图库：seaborn, plotly, plotnine, altair, bokeh, holoviews
- 按需：statsmodels（时序）, xgboost, PyPDF2/pymupdf（读题）, python-docx
- seaborn 替代表：`sns.set_style()`→`plt.rcParams`+`ax.grid(alpha=0.3, ls='--')`；`sns.color_palette()`→`plt.cm.viridis(np.linspace(0.1,0.9,n))`；`sns.heatmap()`→`ax.imshow()`+`colorbar`；`sns.despine()`→隐藏 top/right spines。

## 两阶段执行（先算后画）

每个求解脚本必须按此顺序：

```text
第一阶段（纯计算）：数据加载 → 预处理 → 建模 → 求解 → 得到所有数值结果
第二阶段（检查+绘图）：打印每组数据 min/max/mean/std/CV/amplitude（供论文引用）→ 逐图绘制
```

## 公共头部（scripts/common.py 已封装，求解脚本开头 import 即可）

```python
import sys, os
sys.path.insert(0, r"<技能目录>\scripts")   # 或复制 common.py 到 求解/ 目录
from common import *                        # COLORS, FIG_*, save_fig, save_csv, despine, print_stats
```

common.py 内容要点：
- `matplotlib.use('Agg')` 后端；`warnings.filterwarnings('ignore')`。
- 中文字体回退链（跨 Windows/macOS）：SimHei/Microsoft YaHei/PingFang SC/Heiti TC/Noto Sans CJK 等 + `axes.unicode_minus=False`。
- 学术配色 `COLORS`（primary=#2E5B88 蓝、accent=#E85D4C 红橙、positive=#4A9B7F 绿、neutral=#7F7F7F 灰、light=#B8D4E8 浅蓝），灰度打印可区分。
- 图幅常量：`FIG_SINGLE(5,4)`、`FIG_DOUBLE(10,4)`、`FIG_WIDE(8,3)`、`FIG_SQUARE(6,6)`。
- `save_fig(fig, name_cn)`：300 DPI、bbox_inches='tight'、存 求解/问题X/图片/。
- `save_csv(df, name_cn)`：utf-8-sig 编码（Excel 直开不乱码）。
- `print_stats(series_or_df)`：一次性打印 min/max/mean/std/CV/amplitude。
- `despine(ax)`：隐藏上右边框。

## 绘图硬规则

- 每问至少 4-6 张图，覆盖主要分析维度，多多益善；全文 13-18 张为宜。
- 图内不画标题（set_title 禁止，caption 由论文承担）；图例无边框 `frameon=False`；轴标签含单位。
- 折线图线宽 ≥1.5 带标记点，`fill_between` 加置信带；柱状图柔和色+白边；散点 alpha=0.7。
- 去上右边框；网格 `alpha=0.3, linestyle='--'`；子图编号 (a)(b)(c)。
- 禁止：饼图（改水平条形图）、3D 图（除非真 3D 数据）、图内标题、密集网格、四边完整边框、低分辨率。
- 标注关键统计量（r、p、R²）到图上。
- **每张图绘制代码后必须 print() 该图的关键数据特征**（时间范围/趋势/峰值、R²/MAE、最强相关对、Top5 特征重要性、置信区间等）——后续论文描述必须基于这些真实输出，禁止看着图猜。

## 数据处理规范

### EDA 分流（先判断题目类型）
- 物理/机理题（参数是确定常量）：打印关键参数表→几何关系→量纲验证→物理一致性检查；**不做**直方图/箱线图/异常值清洗。
- 数据驱动题：.info()/.head() → 缺失值报告（缺失率+填充策略及理由）→ 异常值检测（IQR/Z-score+占比）→ 分布可视化 → 相关性热力图 → 分组对比。

### 数据体检（读入即做）
- 编码探测（utf-8 → gbk → gb2312 → latin-1）；检查列数一致性、类型混入、合并单元格、多级表头、隐藏 sheet、底部备注行。
- 大 CSV（>1GB）：chunksize 分块、dtype 优化、category 类型、及时释放中间对象。

### 数据泄露防范（预测类致命项）
- 时序特征用 `shift(1)` 取上一期，禁 `shift(-1)`；滚动特征 `rolling(w).mean().shift(1)` 排除当期。
- 标准化只 fit 训练集；目标编码只用训练集统计；时序按时间划分不打乱。
- 右偏分布 `np.log1p()`；分类变量 One-Hot/Label Encoding 在划分之后做。

### 参数记录
- 所有关键参数注明来源：数据统计 / 文献引用 / 网格搜索三选一（代码注释或 print 说明）。
- 随机算法固定种子（`np.random.seed`/`random_state`）。

## 修错循环与降级

1. 脚本报错：读 traceback 定位 → 修复 → 重跑；同一问题最多重试 3 次。
2. 3 次仍失败：**降级为更简单的模型**（如 LSTM→随机森林→线性回归；NSGA-II→加权和法），保持问题逻辑不变，在结果中记录降级原因。
3. 不陷入无限重试；`Glyph missing from font` 类警告先修字体配置再重跑。

## 优化类专项（极易扣分）

- `scipy.optimize.minimize` 只最小化：最大化取负目标，结果还原正值。
- 不等式约束方向 `fun(x) >= 0`：容量上限写 `C - x >= 0`；写完代入边界点验证符号。
- 不只信求解器 `success`：最优解重新代入全部约束，输出每条约束的值、松弛量、是否活跃。
- 整数变量取整后重新验证可行性；不可行用修复启发式。
- 每个优化变量必须有物理上下界（如绳长 ≤ 500mm）；无约束解违反物理时，在输出中写明对比——评委看重这种工程思维。
- 启发式：固定种子 + ≥5 次独立运行 + 报告均值±标准差。

## 结果落盘

- 数值结果存 `求解/问题X/结果/*.csv`（utf-8-sig）；图存 `求解/问题X/图片/`。
- 所有论文会引用的数值必须能追溯到结果文件或代码输出；论文阶段不重新估算、不换四舍五入口径。
- 问题1产出 `求解/预处理数据.csv` 供后续问题共用。
