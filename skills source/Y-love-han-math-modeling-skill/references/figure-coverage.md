# 图表覆盖与生产绑定规范

## 本文件负责

本文件规定如何把每个 Problem Contract 的小问、数据处理、模型结果、验证和灵敏度/稳健性证据映射为题目自适应的图表覆盖计划，并规定 Python 基线、可选 MATLAB 后端和 Registry 绑定要求。

## 本文件不负责

本文件不凭空生成数据、结果或结论，不规定固定图数、固定三维图数或固定页数，也不把图像文件存在等同于生产证据。最终可信度由 Registry、受控 execution、哈希和 P8 门禁判定。

## 覆盖逻辑

对每个真实 `question_id`，优先检查 `data_overview`、`preprocessing`、`model_result` 与适配题型的 `validation`。Problem Contract 声明 `sensitivity`、`uncertainty`、`pareto`、`scenario`、`mechanism`、`spatial` 或 `network` trait 时，再加入对应角色。没有真实结果或不适用时，计划必须保留缺口或结构化不适用理由，不能用随机示例填充。

`figures plan` 是有意支持的"预初始化规划工作区"：项目尚未 `init` 时也可以对
`--contract` 生成覆盖计划，此时 Registry 快照为空、计划如实暴露缺失的生产
证据，并在项目根目录创建 `.mmflow/figure-coverage-plan.json`（持单写者锁）。
该行为不是状态污染；已初始化项目的计划会从 Registry 取每问 Result IDs。

### 计划输入字段（figures plan 的 contract 契约）

规划器按以下 question 级字段生成计划，全部可选除 `question_id`：

| 字段 | 作用 |
|---|---|
| `question_id` | 必填；与 Result 实体的 question_id 一致 |
| `figure_roles` | 显式角色列表；提供时**替换**默认四基础角色（用于纯理论问等无数据图场景） |
| `validation_traits` | 追加题型角色：sensitivity→sensitivity、uncertainty/uncertainty_quantification→uncertainty、pareto/constraint_tradeoff→pareto、scenario/what_if→scenario、mechanism→mechanism、spatial→spatial、network→network |
| `optional_figure_roles` | necessity=optional 的补充角色，缺失不计失败 |
| `not_applicable_figure_roles` | 结构化豁免列表，每项 `{role, reason}`（reason 非空）；verify 记入报告 `not_applicable` 列表而非 missing |
| `hero_figure_role` | 可选；图表叙事线锚点——指定一张"一图讲完该问答案"的 hero 图（须已在计划角色中）。P8 写作时正文首次引用 hero 图处应完成"数值事实→数学结构→决策含义"三层解读，答辩动线以各问 hero 图为骨架；verify 对 hero 项判定规则不变 |

### 覆盖判定

`figures verify` 与 P8 门禁的覆盖检查规则一致：

- `required` 角色无合格生产图 → FAIL 并列入 `missing`；
- `optional` 角色缺失 → 静默忽略；
- `not_applicable` 角色 → 连同理由列入报告 `not_applicable` 列表，不影响 PASS；
- 合格生产图的判据：status=VALID、question_id/role 匹配、backend ∈ {python,matlab}、artifact_class=production、source_results ⊆ 该问题已声明结果集、information_gain 非空。

生产可视化层可用生成器：趋势（data_overview / data_processing / model_result）、诊断散点（validation）、灵敏度排序与龙卷风图（sensitivity）、流程与架构示意（architecture）、模型管线示意图（model_diagram）、矩阵热力图（heatmap）、分布族（distribution：箱线+小提琴 / ECDF / 直方）、综合评价雷达（radar）、Pareto 前沿（pareto）、收敛轨迹（convergence）、残差诊断（residual_diagnosis）、网络关系（network_graph）、分类对比柱状图（bar_chart）、散点拟合（scatter_fit：含拟合线/基线对照/y=x 参照）、结果对比表（result_table）、空间分布图（spatial_map：点位或栅格）；`generate_all.py` 接受声明式图表计划一次批量产出全部 PNG+sidecar 对，`plotting_common.build_item` 从数据文件自动构造含 input_sha256 的 item 输入。

题型追加角色（sensitivity、uncertainty、scenario、mechanism、spatial）没有一一对应的独立生成器文件时的产出路径：优先用上述通用生成器的参数化形态承载（如 spatial 用 heatmap/network_graph/spatial_map 承载栅格或关系结构、scenario 用 trend/model_result 多曲线、uncertainty 用 distribution/convergence、mechanism 用 architecture），并在 figure 登记的 `information_gain` 中说明映射关系；模型选择章的复杂度-性能权衡散点与肘部曲线归入 `scatter_fit` / `model_result` 角色。确需专用绘图时按"自定义生成器"纪律执行——脚本登记为 production 代码 artifact，经受控 runner 执行并产出 v2 sidecar，覆盖判定只认 role/question_id/backend/契约字段，不限定具体模板文件名。

总体技术路线、问题依赖 DAG、数据血缘和机制图只有在契约中存在真实节点与边时才生成。每张图的 `information_gain` 必须说明它相对于其他图新增了什么判断；重复或装饰图不计入覆盖。

## 生产图契约

生产 figure 必须包含 `question_id`、`role`、`necessity`、`backend`、`generator_artifact_id`、`input_artifact_ids`、`units`、`uncertainty_description`、`information_gain`、`paper_locator` 和 `rendering_audit_id`。image 与 v2 sidecar 必须来自同一个成功的 production execution，sidecar 的图像哈希、source Result 集合和契约字段必须与 Registry 一致。demo、reference、fixture、exploratory 或 unattested 依赖不得升级为生产图。

## 后端与审计

Python/matplotlib 是正式必需图的生产基线，输出目录必须由受控 runner 提供，建议 PNG 300 dpi，并保留可审计的单位、样本量和不确定性信息。MATLAB 只有在项目声明、`.m` 源 artifact、版本、命令、输入/输出哈希和 v2 sidecar 均登记后才可使用；MATLAB 不可用时报告 `NOT_APPLICABLE`，不伪造已执行。

**MATLAB execution 豁免（与 isolation-runtime 的边界对齐）**：受控 runner 只为
Python 程序签发 execution 级证明，因此 backend=matlab 的生产图以"契约三元组"
替代 execution 证明——sidecar 必须记录生成脚本哈希（generator_artifact_id 指向
已登记的 `.m` 源 artifact）、输入闭包哈希（input_artifact_ids 全部 VALID 且带
sha256）与输出图像 sha256，三者与 Registry 登记一致即视同满足"image 与 sidecar
来自同一成功 production execution"的字面要求；缺任一元组项仍按契约违约 FAIL。
该豁免只放宽证明载体，不放宽 artifact_class=production、question/role 匹配和
information_gain 要求。
