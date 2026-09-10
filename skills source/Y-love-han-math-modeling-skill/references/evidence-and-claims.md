# 证据实体、血缘、结果与论文绑定规范

## 目录

- [本文件负责](#本文件负责)
- [本文件不负责](#本文件不负责)
- [身份与版本](#身份与版本)
- [Artifact 与 Execution](#artifact-与-execution)
- [Result Registry](#result-registry)
- [Claim Registry](#claim-registry)
- [其他 Registry 实体](#其他-registry-实体)
- [Lineage DAG 与失效传播](#lineage-dag-与失效传播)
- [复现比较](#复现比较)
- [LaTeX 精确绑定](#latex-精确绑定)
- [选择性报告控制](#选择性报告控制)
- [代码注释溯源标签参考](#代码注释溯源标签参考)
- [阶段验收](#阶段验收)
- [附录：v2 证据实体锁](#附录：v2 证据实体锁)

## 本文件负责

本文件是 P5–P9 运行、产物、结果、主张、公式、图、引用、审查证据、血缘、复现比较和论文绑定语义的唯一规范。
它解决“这个数字和结论究竟来自哪里、现在是否仍有效”。

## 本文件不负责

本文件不选择模型、不判定某验证适配器是否充分、不核验当届格式，也不赋予 AI 最终奖项判断权。
Registry 中存在记录只证明记录可追踪；主张强度还必须由适用验证和审查决定。

## 身份与版本

每个竞赛任务使用唯一 `run_id`。
每次模型或修复尝试使用唯一 `attempt_id`。
每次受控进程启动使用唯一 `execution_id`。

正式实体使用类型前缀和当前运行内唯一 ID：

- `artifact_id`：文件或结构化产物；
- `result_id`：带完整语义的数值或类别结果；
- `claim_id`：论文主张；
- `formula_id`：公式、推导或经验常数；
- `figure_id`：图及其侧车数据；
- `citation_id`：外部来源；
- `finding_id`：审查缺陷；
- `evidence_id`：阶段证据对象。

Registry 只追加新版本，不覆盖旧记录。
记录文件名包含实体 ID、版本和记录哈希；每个记录必须由账本事件提交。
同一 ID 不能跨实体类型复用，其他运行的记录不能导入当前运行充当证据。

实体 `status` 为 `VALID`、`STALE`、`INVALID` 或 `REVOKED`。
`artifact_class` 与 `status` 分离：合法 demo 可以是 `VALID`，但仍不能支撑生产主张。

## Artifact 与 Execution

artifact class 只允许：

| 类别 | 用途 | 能否支撑确认性论文主张 |
|---|---|---|
| `production` | 受控生产运行的冻结输入或输出 | 满足所有依赖时可以 |
| `exploratory` | 探索、调试和发现假设 | 不可以，需冻结后重跑 |
| `demo` | 教学或界面演示 | 不可以 |
| `fixture` | 测试夹具和恶意回归 | 不可以 |
| `external` | 已核验的外部数据或规则 | 按来源强度决定 |
| `unattested` | 未经受控执行证明的文件 | 不可以 |

artifact class 一经登记不可提升。
把 demo 改名、复制到结果目录或更改扩展名仍是 demo。

生产 execution 必须逐项绑定当前运行、`VALID` 的 source artifact：

- 数据输入；
- 源代码及导入模块；
- 配置；
- 环境或依赖描述；
- 随机性和命令参数；
- 预期输出清单；
- 每个输出的比较策略和容差。

受控 runner 在全新空 attempt/sandbox 中复制并快照源文件，使用参数数组且 `shell=False`。
禁止从含 demo、fixture 或归档语义的路径创建 production 源证明。

runner 在启动前预登记输出；运行后记录新增、修改和删除文件。
缺失输出、额外输出、符号链接或重解析点、沙箱外写入、非零退出、超时、启动失败和用户中断均使 production execution 无效。

原始 stdout/stderr 字节先保存并计算哈希，再生成 UTF-8 视图。
无法无损解码时登记 `lossy=true`，不能丢弃原始字节。

只有状态为 `VALID` 的当前运行 production execution 才能产生 production output artifact。
输出登记后文件内容变化必须检出并沿血缘失效。

## Result Registry

每个 Result 至少包含：

- `result_id` 与 `run_id`；
- `artifact_id` 和 `execution_id`；
- `metric`：指标的语义名称；
- `value`：有限数值、类别或结构值；
- `unit`：物理或统计单位；
- `direction`：越大越好、越小越好、目标最佳或不适用；
- `scenario`：情景、参数和对象；
- `dataset_split`：训练、验证、测试、回测窗口或全量描述；
- `sample_size`：与分析单位一致的正整数或结构；
- `source_locator`：JSON Pointer、表行列或其他结构定位；
- `display`：论文显示值、舍入规则和有效位数；
- 不确定性、估计区间或重复运行摘要中的适用项；
- `status` 与依赖。

Result 登记时从源 artifact 的结构化位置重新解析值和语义，不信任调用方手填的重复值。
同一个数值若指标、单位、场景、划分或样本量不同，是不同结果。
数值相等不能建立实体等价。

禁止 NaN、Infinity、布尔冒充数值、非法样本量和与预登记舍入不一致的显示值。
默认十进制显示采用明确的 half-even 或项目冻结规则，论文不得另行手工四舍五入。

派生比例、差值、改善率、排名和汇总必须登记 derivation，引用源 result ID，并由系统重新计算。
不能在论文中凭记忆填写“提升百分比”。

## Claim Registry

每个 Claim 至少含：

- `claim_id`、类型和精确文本；
- `supports`：Result、Formula、Citation 或 Evidence ID；
- `derivation`：从支持实体到文本的转换；
- `scope`：时间、空间、总体、情景和外推边界；
- `counterevidence`：反证、失败情景和不一致结果；
- `strength`：confirmed、supported、exploratory、hypothesis 或 unsupported；
- 适用要求和论文位置；
- `status`。

主张类型包括 computed、observational、inferential、theoretical、external、recommendation 和 limitation。
类型决定可接受证据；外部文献不能替代当前数据中的计算结果，预测分数不能单独支撑因果主张。

主张强度规则：

- `confirmed`：预登记、适用验证、独立或外层证据和反证均通过；
- `supported`：多项一致证据支持，但存在范围或独立性限制；
- `exploratory`：查看结果后形成或缺独立确认；
- `hypothesis`：待验证机制或解释；
- `unsupported`：证据失败或矛盾，不能进入结论。

摘要核心主张必须具有足够强度，并绑定精确证据。
若反证使范围缩小，创建新 Claim 版本，不能只改论文措辞而保留旧实体。

### P7 收尾红队预审（对抗审查前移）

P7 结束、进入 P8 写作之前，对每个 `global_optimum`、`causal`、
`confirmed` 强度或支撑论文主贡献的 Claim 执行一次轻量红队预审：
用 `templates/quality/redteam_claim_drill.py --claims <export-claims 输出>`
生成攻击面清单，逐条填写"既有验证覆盖"或标记缺口；缺口按影响登记为
需回补的验证项（回 P6）或直接降级主张强度。预审记录写入决策摘要，不产生
新的必需证据类型；其价值是把 P10 五角色审查中最高频的 CRITICAL/MAJOR
来源（最优性无证书、因果越界、稳健性缺失）在写作前消灭，显著降低
后期回退成本。

## 其他 Registry 实体

### Formula

Formula 记录定义、符号、单位、前提、推导、外部定理、经验常数来源、边界和验证证据。
公式中来自题面、规则、文献或实验的数字必须分类并绑定，不因出现在数学环境中而豁免。

### Figure

Figure 绑定图像 artifact、侧车数据 artifact、生成 execution、源 result、caption claim、轴与单位、尺度、不确定性和审计风险。
只登记 PNG 哈希而无侧车数据不能证明图中数值正确。

### Citation

Citation 记录来源元数据、访问等级、具体支持位置和支持的 Claim。
引用存在不等于支撑文本准确；需核对前提和范围。

### Finding

Finding 含严重度、证据位置、受影响 Claim、最早回退阶段、重跑范围、状态和 closure evidence。
关闭 finding 需要真实新证据或主张降级，不能只把状态改为 closed。

### Evidence

Evidence 是阶段门禁使用的结构对象，类型由版本化 schema 定义。
它可聚合实体 ID，但不能嵌入一段无来源文字代替实体。

## Lineage DAG 与失效传播

Lineage 至少包含以下边：

- execution → source artifacts；
- production artifact → execution 与 inputs；
- result → artifact 与 execution；
- claim → supports 与 counterevidence；
- figure → image、sidecar、results 与 claims；
- formula、citation、finding、evidence → 各自依赖；
- manuscript binding → result、claim、formula、citation 与规则值。

依赖图必须无环；未知依赖 fail closed。

上游输入、代码、配置或外部数据被判为错误时，根实体可变为 `INVALID` 或 `REVOKED`。
所有可达后代传播为 `STALE`，包括执行、产物、结果、图、主张和稿件。
后代保持 `STALE`，不能因为根改为 `REVOKED` 而伪装成未受影响。

恢复时创建新 execution 和实体版本，重新连接依赖。
不得把旧 result 的状态直接改回 `VALID`；必须证明新血缘。

## 复现比较

预登记输出比较策略只允许：

- `sha256`：字节必须完全一致；
- `json_exact`：规范化 JSON 结构和值完全一致；
- `json_numeric`：结构一致，有限数值按预登记绝对或相对容差比较；
- `statistical_json`：结构一致，数组按预登记统计等价规则比较（多种子/多次重复的均值、标准差与置信区间，配合随机协议使用）。

四种模式与 `references/isolation-runtime.md` 及受控 runner 实现一一对应；随机算法、GPU 训练和多种子协议必须使用 `statistical_json`，不得用 `json_numeric` 收紧容差来冒充统计等价。

容差必须在首次生产运行前登记，非负、有限并有指标尺度依据。
复现失败后不能为了通过扩大容差。

随机算法不一定要求输出字节相同，但必须预先定义统计性质、种子模式、置信范围和重复次数。
如果策略没有定义随机比较，默认不能声称复现通过。

隔离复现使用新的 attempt、冻结源快照和空输出目录。
复现报告引用原 execution、新 execution、每个输出比较、环境差异和最终状态。

## LaTeX 精确绑定

稿件使用以下显式宏表达来源语义：

- `\MMResult{result_id}`：结果显示值（单参数；源定位以 Registry 中该 result 的 locator 为权威）；
- `\MMResultWithUnit{result_id}`：值与单位（单参数，同上）；
- `\MMClaim{claim_id}{精确文本}`：登记主张；
- `\MMGiven{evidence_id}{field_pointer}`：题面或给定值；
- `\MMCitedValue{citation_id}{field_pointer}`：外部来源值；
- `\MMFormulaConstant{formula_id}{field_pointer}`：公式常数；
- `\MMRuleValue{requirement_id}{field_pointer}`：当届规则值（第一参数为 `competition_rules` 的 `requirement_id`，不是 evidence_id 或 citation_id）。

宏签名以受控渲染器实现为唯一权威（`scripts/mmflow_core/bindings.py` 的宏-参数表）；本节与 `paper-and-visuals.md` 附录一致。历史版本中 `\MMResult` 双参、`\MMRuleValue` 以 evidence_id 开头的写法已废弃，不得使用。

渲染器解析平衡花括号、嵌套文本和注释，按 Registry 与 JSON Pointer 取值。
对 Result 核对指标、单位、方向、情景、划分、样本量、源 artifact、execution 和显示舍入，而不只比较数值。

`\MMClaim` 文本必须与当前 Claim 版本一致。
其中的计算数字必须来自支持实体；相同数字出现在无关 CSV 中不能使主张通过。

渲染后生成 binding manifest，记录每个宏、实体版本、源定位、解析值和稿件位置。
P8、P9 和最终 audit 都重新验证 manifest 与文件哈希。

裸科学数字扫描覆盖正文、表格、图注和公式环境。
公式编号、章节号、索引和纯符号结构可按明确规则忽略；经验常数、实验结果、阈值和外部事实不能整体豁免。

全局数字池被禁止。
在项目任意文件中搜索到相同字面量，不构成来源证明。

## 选择性报告控制

保留所有 production 和 exploratory attempt，包括失败、不收敛、较差种子、无效假设和反证。
论文可以聚焦核心结论，但 Registry 和审查必须看到完整实验族。

预登记主指标不能因不显著而被次指标替换。
若展示多个指标，说明选择规则并报告方向和不确定性。

主张不能只引用最佳运行；需要引用预登记聚合、重复分布或明确的确定性执行。
图表不得只挑有利时间窗、子群或坐标范围。

## 代码注释溯源标签参考

为增强代码可审计性，可在关键代码段添加溯源注释标签。标签是可选的辅助手段，不替代 Artifact、Execution 和 Result 的正式绑定；代码溯源信息最终仍由 Registry 中的 execution_id 和 source_locator 确认。

### 标签格式

在关键代码段（模型核心逻辑、数据处理、结果计算）的注释中使用以下格式：

```
# @source: formula_id=F-002, theorem=Jensen不等式
# @source: result_id=R-015, execution_id=E-008
# @source: citation_id=C-003, page=42
# @source: given_id=G-001, field=常数α
```

### 适用范围

- 模型核心公式的代码实现段。
- 关键数据处理或特征工程段。
- 结果计算和输出段。
- 调用外部定理或文献参数的代码段。

### 约束

- 标签中的实体 ID 必须在当前运行 Registry 中存在且为 `VALID`。
- 标签不替代正式绑定：论文中的数字仍必须通过 `\MMResult` 等宏绑定到 Registry。
- 标签信息与 Registry 不一致时以 Registry 为准；标签错误登记为 finding 并修正。
- 简单工具脚本或探索性代码不需要标签；只对进入 production execution 的代码段使用。

## 阶段验收

P5–P9 通过前必须证明：

- 所有 production output 来自当前运行有效受控 execution；
- demo、fixture、unattested、跨运行和陈旧实体未支撑最终主张；
- Result 具有完整语义且从结构化来源解析；
- Claim 的类型、范围、强度、支持和反证一致；
- Figure 有图像、侧车、执行、结果和 caption claim 血缘；
- Lineage 无环，未知依赖和上游变化会 fail closed；
- 论文每个科学数字和核心主张通过实体绑定；
- 复现按冻结策略比较，容差未事后修改；
- 失败和不利结果没有被删除或隐藏。

Registry 记录数量、文件名或文字声明不能自证质量；门禁必须验证记录文件、事件提交、源文件哈希和完整依赖。


## 附录：v2 证据实体锁

### 证据依赖提取

- 每种证据类型在 `schemas-v1.json` 的 `evidence_dependency_fields` 中声明内容依赖路径；Registry 在注册时从 content 确定性提取实体 ID，并要求与显式 `supports` 完全相等。漏报、多报或虚报一律拒绝。
- 血缘图只使用程序提取后的依赖集合，防止"内容里引用了实体、supports 却没写"的引用绕过失效传播。

### 注册阶段矩阵

- 每种证据类型只能在 `evidence_stage_matrix` 允许的阶段登记；未来阶段证据（如 P0 登记 P10 的 review_findings）被拒绝。
- 阶段绑定实体（result、claim、formula、figure、finding、evidence）必须存在活动阶段；记录携带 `created_stage`、`stage_epoch` 与 `created_ledger_sequence`。

### Finding 关闭

- finding 必须声明 `affected_entities`、`affected_claims` 与 `rerun_scope`。
- 关闭必须提供结构化 `finding_closure`：`finding_id`、`affected_entities`、`repair_entities`、`rerun_gates`（每项含 stage、report_sha256、gate_event_sequence）。
- 关闭条件：关闭证据引用该 finding、晚于其创建且当前 VALID；受影响实体恢复为 VALID 或由 VALID 修复实体替换；重跑门禁晚于 finding、为 PASS、报告哈希与账本一致；重跑范围覆盖 `rerun_scope`。普通有效证据不能关闭 finding。

### Result / Claim / Formula / Citation

- Result 的 `result_kind`、方向、样本量、uncertainty 上下界与 display 舍入受严格检查；source_locator 必须解析到生产 artifact 中的真实字段并逐字段核对。
- Claim 强度与支持实体类型受约束：confirmed 需要程序事实支持；counterevidence 存在时必须降级。
- MMRuleValue 绑定 `competition_rules` 的 requirement_id 与字段指针，不再把 Citation 当规则值。
- Figure 的图像与 sidecar 必须同为 production、来自同一次绘图 execution、sidecar 使用固定 schema、记录图像 SHA-256，且 source_result_ids 与 Figure Registry 完全一致。



### 数据集划分（dataset split）实体

- 划分是独立不可变实体（`register-split`）：`source_dataset_artifact_id`、`split_kind`（time/group/spatial/random/custom）、`selectors`、`indices_sha256`、`leakage_boundary`、`preprocessing_fit_scope`（train_only/none）、`immutable_fingerprint`。
- Execution 的 `dataset_split_ids` 与 Result 的 `dataset_split_id` 必须引用当前 VALID 的 split 实体；字符串自报不能证明哪些样本被隔离、时间边界、群组边界或预处理拟合范围。

### Formula 契约（formula-v1）

- formula 必须是可检查的科学对象：`expression`、`symbols`（命名对象表）、`premises`、`derivation`、`boundary_cases`，且按类型强制：theoretical 需要 `theorem_conditions` 与推导；empirical 需要 `data_basis` 与 `fitting_evidence`；optimization 需要 `objective` 与 `constraints`；statistical 需要 `assumptions` 与 `uncertainty`。

### Citation 契约

- citation 必须携带 `authors`、`year`、`version`、`source_url`、`access_level`（public/subscribed/private/deleted）、`verification_status`（verified/corrected/unverified/failed/retracted）、`source_role`（official_rule/academic/dataset/web/other）、`metadata_verification` 对象与可选 `source_locator`/`content_support_verification`/`supports_claims`。
- P3 只接受 metadata 已核验（verified/corrected）且未删除的引用；retracted/failed/unverified 不能进入文献库。程序可验证的是 URL、哈希、元数据与访问时间；正文是否真正支持主张属于专业核验；文献结论的现实真实性不可由程序保证。
