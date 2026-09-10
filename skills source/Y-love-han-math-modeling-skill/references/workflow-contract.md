# 自主工作流、状态与恢复规范

## 目录

- [本文件负责](#本文件负责)
- [本文件不负责](#本文件不负责)
- [事实来源与信任边界](#事实来源与信任边界)
- [状态机](#状态机)
- [阶段门禁](#阶段门禁)
- [事件账本与派生视图](#事件账本与派生视图)
- [命令生命周期](#命令生命周期)
- [失败恢复](#失败恢复)
- [阻塞协议](#阻塞协议)
- [退出码](#退出码)
- [阶段验收](#阶段验收)
- [附录：v2 程序锁](#附录：v2-程序锁)

## 本文件负责

本文件是 P0–P11 工作流、状态、门禁、恢复、命令生命周期和退出码语义的唯一行为规范。
在新任务启动、旧任务恢复、阶段推进、上游变更和完整性异常时读取。
本文件规定“什么状态可以发生”和“什么证据允许推进”，不以语言风格判断专业质量。

## 本文件不负责

本文件不选择模型，不定义具体统计检验，不判断某条竞赛格式事实，也不规定论文内容。
模型、验证、数据、主张、合规和写作各由对应单一职责规范约束。
状态机只确认证据契约和检查结果，不把阶段通过解释成最终奖项事实。

## 事实来源与信任边界

工作流事实只来自以下机器对象：

1. 版本化策略锁；
2. 事件账本与已提交的 `ledger-head.json`；
3. 追加式 Registry 记录；
4. 受控执行证明；
5. 带哈希的门禁报告；
6. 从账本重放得到的派生状态。

文件名、章节关键词、文件大小、成功提示、AI 自报和手工清单均不是通过证据。
AI 可以创建证据候选、请求检查和修复失败，但不能自行宣布检查器通过。
AI 无权直接写入 PASSED；`PASSED` 只能由新鲜门禁报告和合法 `advance` 事件导出。

策略锁覆盖活动 `SKILL.md`、唯一 CLI、确定性内核、策略 JSON、直接参考规范和生产模板。
任务初始化后策略内容变化即造成完整性失败，除非建立明确的新策略版本和新运行。
不得通过只更新哈希值掩盖运行时文件变化。

本地系统无法防御拥有完整文件系统权限且同时重写内核、全部事件、锁和哈希的恶意主体。
更强保证需要宿主只读权限、外部签名或远程不可变日志；本地报告必须披露此边界。

校验分两层执行。常规命令始终运行账本结构校验（事件文件名即内容哈希构成的链、计数与提交头一致、尾事件体深检），
并在每次读取 Registry 记录时逐条验证记录哈希与账本登记一致；
全量逐事件内容重放只在信任前沿变化后的首次加载，以及 `gate` 后的 `audit`、`release-status` 和迁移应用等强制节点运行。
该分层以"交付前必经的 audit 级深检"为前提，用于把常规命令成本压到近常数；
任何完整性异常仍按 `INTEGRITY_FAILURE` 处理，不因分层而降级。

## 状态机

合法主序列为：

`P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 → P9 → P10 → P11 → COMPLETE`

阶段状态含：

| 状态 | 含义 | 可执行动作 |
|---|---|---|
| `NOT_STARTED` | 尚未成为活动阶段 | 等待前序推进 |
| `ACTIVE` | 当前唯一可工作的阶段 | 登记证据、运行门禁、阻塞或回退 |
| `GATE_FAILED` | 最近门禁为失败或错误 | 在同阶段修复并重新门禁 |
| `PASSED` | 已由门禁合法推进 | 只读；上游失效时可变为 `INVALIDATED` |
| `INVALIDATED` | 上游变化使既有结论陈旧 | 回到最早受影响阶段重做 |
| `BLOCKED` | 缺少不可替代的外部输入或权限 | 提供最小请求后显式恢复 |
| `INTEGRITY_FAILURE` | 策略、账本或报告无法验证 | 停止专业工作，先恢复完整性 |
| `COMPLETE` | P11 合法推进后的终态 | 允许生成最终本地交付说明 |

任何时刻最多一个主阶段为 `ACTIVE`。
不能在 P2 活动时开始 P3，也不能同时让两个阶段活动。
P11 的门禁通过不等于终态；只有 P11 的合法 `advance` 才导出 `COMPLETE`。

赛制确实没有选题、附件、答辩等环节时，不删除阶段。
把对应子要求按规则登记为 `NOT_APPLICABLE`，同时保留阶段中其他适用检查。
自然语言“本题不需要”不能替代规则标识、Problem Contract 条件和有效 waiver 证据。

## 阶段门禁

每个阶段门禁读取版本化证据策略，至少完成：

- 检查必需 evidence 类型是否齐全且属于当前 `run_id`；
- 检查实体状态为 `VALID`，并验证依赖没有 `STALE`、`INVALID` 或 `REVOKED`；
- 执行阶段语义检查器；
- 汇总当前运行的活动红线；
- 生成规范 JSON 报告和中文 Markdown 报告；
- 在事件账本中引用两份报告及其哈希。

检查状态仅允许：`PASS`、`FAIL`、`ERROR`、`BLOCKED`、`NOT_APPLICABLE`。
聚合优先级为 `ERROR > FAIL > BLOCKED > PASS`；合法的 `NOT_APPLICABLE` 对聚合中性。
未知状态、空检查集合、检查器异常、缺失报告、报告损坏或无依据豁免必须 fail closed。

门禁通过具有新鲜度。
登记新实体、修改上游产物、传播陈旧状态、关闭或新增 finding 后，旧报告不得继续推进。
`advance` 必须核对阶段、策略哈希、账本 head、报告哈希、生成时序及当前 Registry 状态。

门禁失败时保留失败报告。
修复后生成新的报告版本，不覆盖旧报告，不手改状态，不把失败文本替换成成功文本。

## 事件账本与派生视图

每次任务使用唯一 `run_id`。
每个事件单独保存，以零填充序号和事件 SHA-256 命名，并引用前一事件哈希。
事件内容使用规范化 JSON，禁止 NaN、Infinity 和依赖平台的非确定性序列化。

`ledger-head.json` 是原子提交指针，包含当前序号、事件哈希、策略哈希和 generation。
追加事件使用事务记录：先写候选事件和事务，再原子更新 head，最后删除事务。
恢复时只允许提交被完整事务描述、前序链接正确且策略一致的候选事件。

以下均为完整性错误：

- 删除尾事件或中间事件；
- 篡改事件内容；
- 重复或非规范事件文件名；
- 没有事务支持的孤儿事件；
- head 自哈希不一致；
- 候选事件引用错误前序或错误运行；
- 策略哈希与初始化时不一致。

`state.json` 只是派生视图，不是事实来源。
每次 `status` 或变更命令都从事件重放；若手工视图与重放结果不同，重建视图并记录不一致事件。
不得把手工编辑的 `state.json` 当作推进依据。

## 命令生命周期

唯一入口是 `python <skill-root>/scripts/mmflow.py`。
机器输出使用 `--json`，必须保持 ASCII 可解码；诊断信息不得污染标准输出中的 JSON。

| 命令 | 契约 |
|---|---|
| `doctor` | 只读检查 Python、文件系统、网络、LaTeX、PDF 与可选审查能力；缺能力要明确报告 |
| `init` | 在未初始化项目中创建 run、策略锁、账本、Registry 和派生视图；不覆盖现有运行 |
| `status` | 验证策略、账本、Registry、报告和产物；重放并返回当前状态 |
| `next` | 返回唯一合法下一动作、阶段和需读参考；不改变状态 |
| `begin` | 只允许启动序列中的下一阶段；不能跳级 |
| `gate` | 运行当前阶段所有检查，保存双格式报告并登记事件 |
| `advance` | 只接受当前阶段新鲜 `PASS` 报告；推进一次 |
| `rollback` | 激活最早受影响阶段，使下游阶段和实体失效 |
| `run` | 在全新沙箱执行预登记命令；生产运行要求完整输入证明 |
| `register-*` | 追加登记实体版本；禁止覆盖和跨运行引用 |
| `render-bindings` | 从 Registry 解析论文绑定并生成 manifest |
| `scan-manuscript` | 检出未绑定的经验或科学数字及未解析标记 |
| `reproduce` | 从冻结源在空目录重跑并按预登记策略比较 |
| `review` | 登记结构化 finding，不直接清除红线 |
| `audit` | 只读核验完整性、血缘、论文、合规和交付候选 |
| `package` | 按白名单创建本地候选包或最终包，不执行上传 |
| `checkpoint` | 保存恢复所需的账本 head、阶段、风险和下一命令摘要 |
| `resume` | 先验证并恢复事务，再返回精确下一动作 |
| `close-finding` | 关闭 finding：`--id <finding_id> --closure <closure.json> --reason <...> [--mode CLOSED\|ACCEPTED_LIMITATION]`；关闭证据必须晚于 finding 且当前 VALID，并覆盖 `rerun_scope` |
| `schema` | 只读自省：输出证据内容契约、依赖提取路径、实测字段注记与八维分值（`--evidence-type` 可过滤；不需要项目） |
| `adapters` | 只读自省：输出全部合法 trait/claim_type/model_family 的验证适配器机器名与 waiver 规则 |
| `cookbook` | 只读自省：输出阶段必需证据集合、参考路由与登记手册路径（`--stage Pn` 可选） |
| `figures plan` | 从 Problem Contract 与 Registry 结果生成题目自适应图表覆盖计划（写入 `.mmflow/figure-coverage-plan.json`；持单写者锁） |
| `figures verify` | 对照已登记 Figure 核验图表覆盖计划的完成度 |
| `export-claims` | 导出 VALID claim 及其支撑实体为答辩卡片输入 JSON（`--question` 可过滤，`--output` 落盘） |
| `batch-register` | 从单个 JSON 文件批量登记实体（顶层 `{entries: [{kind, payload}]}`；单条失败记为 ERROR 行，不中断其余条目） |
| `invalidate` | 失效实体并沿血缘传播：构建完整后代集合、计算最早回退阶段与重跑范围，并在单个事务内完成失效和回退（`--id <entity> --reason <...>`） |
| `promote-artifact` | 维护入口：为已登记且内容未变的 production artifact 重绑同 run 的有效 execution（`--id <artifact_id> --execution-id <exec_id>`）；载荷全量复验，artifact_class 本身不可变，非 production 类拒绝 |
| `scan-privacy` | 扫描 delivery manifest 全部成员（秘密、绝对路径、PDF 元数据、EXIF、嵌套压缩包、违禁文件名），写不可变报告（持单写者锁） |
| `release-status` | 只读：校验完整性后程序计算发布标签；未 COMPLETE 时预期 NOT_READY 与退出码 3，属设计行为 |

维护工具（不属于状态机命令面，直接操作 Registry/工作流时必须持有单写者锁）：

- `python scripts/heal_mismatch.py --project <root> [artifact_id ...]`
  对"内容已变的 VALID artifact 根"做秩守卫失效并回退到最早受影响阶段，
  用于从 `monotonic` IntegrityError 中恢复。
- `mmflow retire-artifact --id <entity> --reason <...>`
  代际重建入口：把指定实体（通常为上一代固定路径 artifact）标记 `STALE`
  并沿血缘传播后代失效，**不自动回退阶段**；返回
  `suggested_rollback_stage` 与 `rerun_scope`，由调用方显式决定是否执行
  `rollback`。这是"同路径单制品"重生成前的规范操作，替代任何直接改写
  实体状态的手工尝试。

对外没有绕过这两个工具直接改写单个实体状态的命令；`mmflow invalidate --id
<entity> --reason <...>` 构建完整后代集合、计算最早回退阶段与重跑范围，
并在单个事务内完成失效和回退。

所有会改变运行事实的命令必须先验证策略锁、账本和运行身份。
CLI 可从项目外目录调用；路径解析以明确的 skill 根和项目根为准，不依赖当前目录。

## 失败恢复

发生模型、数据或论文失败时按以下顺序恢复：

1. 保存原始错误、标准输出、标准错误和失败 attempt；
2. 找到最上游根因，而不是改最终文本；
3. 登记受影响根实体为 `INVALID` 或 `REVOKED`；
4. 沿 Lineage DAG 将下游实体传播为 `STALE`；
5. `rollback` 到最早需要重新决策的阶段；
6. 创建新的 `attempt_id` 和 `execution_id`；
7. 只重跑最小受影响子图；
8. 重新生成结果、绑定、报告和阶段门禁。

输出漂移、代码变化、数据变化或容差策略变化都不能通过覆盖旧记录解决。
复现失败后不得扩大容差；需要改变比较策略时，必须回退到冻结分析计划并把既有结论降级。

账本事务中断时先执行恢复。
若候选事件不完整或不满足事务条件，保持上一个已提交 head 并报告错误，不猜测用户意图。

### Skill 版本演进与进行中项目

策略锁覆盖活动 `SKILL.md`、CLI、内核、策略 JSON、直接参考规范和生产模板。
因此安装目录的 Skill 内容在项目初始化之后发生任何变化（包括参考文档修订），
都会使旧项目的下一次完整性校验失败；这是设计行为，不是损坏。

出现因策略内容变化导致的 `INTEGRITY_FAILURE` 时，按以下顺序处置：

1. 停止专业工作；运行 `doctor` 与 `audit` 确认失败原因确为策略锁不匹配，而非真实篡改或数据损坏。
2. 二选一，并登记决策摘要：
   - **沿用旧版本收尾**：从备份或发布归档恢复与策略锁一致的旧 Skill 副本，用它完成当前项目；旧副本保持只读。
   - **迁移到新版本**：冻结旧项目的全部产物哈希与状态报告，用新 Skill 对同一题目重新 `init`，
     把旧产物作为带哈希与来源说明的外部输入重新读取和核验；不得手工改写旧锁、旧账本或旧哈希来"适配"新版本。
3. 禁止通过直接编辑策略锁、重算哈希或删除账本事件使新旧版本"看起来一致"。

维护者纪律：对 Skill 源的全部文档与代码修改应合并为单个批次一次完成；
频繁零散修改会反复打断所有进行中项目。

## 阻塞协议

只有关键外部输入、授权或不可替代能力缺失时才进入 `BLOCKED`。
模型难调、实验失败、论文需要重写和需要更多计算不是阻塞理由。

阻塞记录必须包含：

```json
{
  "missing_item": "所缺最小对象",
  "why_required": "它决定哪项要求、变量或约束",
  "attempted_alternatives": ["本地附件", "一手公开来源", "合法代理分析"],
  "minimum_request": "只请求恢复工作所需的最小字段或授权",
  "safe_partial_outputs": ["仍然有效且不依赖缺失项的产物"],
  "resume_command": "精确恢复命令"
}
```

恢复必须是显式事件，并核验缺失条件确实改变。
不能通过删除阻塞记录或把 `BLOCKED` 改成 `PASS` 恢复。

## 退出码

| 退出码 | 含义 |
|---:|---|
| 0 | 命令成功，或只读状态成功返回 |
| 1 | 未捕获内部异常（INTERNAL 信封）；绝不能解释为通过，需结合 message 定位后重试或报告缺陷 |
| 2 | 参数、路径、JSON 或 schema 错误 |
| 3 | 门禁或合规检查失败 |
| 4 | 策略、账本、Registry、报告或哈希完整性错误 |
| 5 | 缺少外部输入、权限或授权而合法阻塞 |
| 6 | 内部检查器异常；绝不能解释为通过 |
| 7 | 环境能力缺失或不兼容 |
| 8 | 请求使用不可信、跨运行、未证明或陈旧产物 |

调用方必须依据退出码和结构化状态处理失败，不能只搜索“成功”字样。

## 阶段验收

启动或恢复工作流前必须能够证明：

- 策略锁自哈希和所有活动文件哈希一致；
- 事件链、head 和未完成事务处于可验证状态；
- 当前 `run_id` 唯一，派生状态可由账本重建；
- 最多一个阶段活动，阶段顺序无跳跃；
- 最近门禁报告的 JSON、Markdown 和事件引用一致；
- 所有异常以非零退出码 fail closed；
- 阻塞记录包含最小请求和恢复命令；
- `COMPLETE` 只能由 P11 合法推进产生。

任何一项无法证明时，停止下游建模和写作，先恢复完整性或报告 `NOT_READY`。


## 附录：v2 程序锁

以下程序锁是 v2 行为契约的强制部分，v1 项目保持只读可验证，不静默迁移。

### 单写者锁与崩溃恢复

- 所有修改状态的 CLI 命令（init、begin、gate、advance、rollback、register-*、run、render-bindings、reproduce、review、close-finding、invalidate、batch-register、promote-artifact、retire-artifact、package、checkpoint、audit、scan-privacy、resume）必须先获取 `.mmflow/project.lock` 的 OS 级排他锁；锁中记录 PID、进程启动时间和 run_id，但持有权由操作系统判定，不依赖锁文件存在与否。`figures plan` 写入计划时同样持该锁。
- Registry 记录写入采用两阶段日志：先写 `registry-journal.json`（PREPARED），再写记录文件，最后追加 `REGISTRY_RECORDED` 事件并标记 COMMITTED。崩溃后恢复是确定性的：账本中已有该记录事件则只清除日志，否则删除未提交记录文件。
- 两个并发 gate 不会覆盖报告：报告序号在同一把锁下分配。

### 阶段 epoch 与证据新鲜度

- 每条 Registry 记录携带 `created_stage`、`stage_epoch` 和 `created_ledger_sequence`。
- `begin`、回退到某阶段、从阻塞恢复都会使该阶段 epoch 递增。
- 门禁只接受：本阶段当前 epoch 的证据；或证据类型明确允许跨阶段继承且来源阶段当前为 `PASSED` 的证据。`VALID` 状态本身永远不是充分条件。
- 回退自动使目标阶段及下游实体（除不可变 external 输入）变为 STALE；被回退代次的证据不能复活。

### 原子 BLOCKED 与恢复证据

- BLOCKED 是单一原子状态事件，载荷必须含 `missing_item`、`why_required`、`attempted_alternatives`、`minimum_request`、`safe_partial_outputs`、`resume_command` 六个字段。
- `resume --resolve-blocked --evidence <id>` 只接受：阻塞事件之后创建、当前 VALID、且为 evidence 实体的恢复证据；恢复后进入新 epoch 并重新执行门禁，不恢复旧门禁结果。

### 错误分类

- 业务证据不满足 → `FAIL`（`EvidenceInsufficientError`）。
- 外部必要资源不可得 → `BLOCKED`（结构化载荷）。
- Registry、策略、哈希或状态完整性错误 → `ERROR` / `CRITICAL`。
- 未预期异常 → `ERROR` / `CRITICAL`；任何未知异常都不得被解释为普通业务失败。

### 失效与发布

- 对外没有直接改写单个实体状态的命令；`mmflow invalidate --id <entity> --reason <...>` 构建完整后代集合、计算最早回退阶段与重跑范围，并在单个事务内完成失效和回退；代际重建（不回退阶段、只退役上一代制品）使用 `mmflow retire-artifact` 维护入口。
- `mmflow release-status --project <root> --json` 从 Registry、门禁、红线、审查独立性和交付状态程序计算发布标签；调用方不能传入标签。

### 只读 doctor 与隔离披露

- `doctor` 默认只读：不创建项目目录、不写探针；需要验证可写性时显式加 `--probe-write`。
- `doctor` 输出必须披露隔离等级：`os_sandbox=false`、`network_isolation=false`、`external_filesystem_isolation=false`，隔离等级为 `project-directory-attestation`。

### checkpoint v2 与 next 工作队列

- checkpoint 记录工作队列：缺失证据、失效实体、重跑范围、开放风险与未完成事务。
- `next` 返回唯一行动对象：stage、stage_epoch、references、next_command、missing_evidence、invalid_entities、rerun_scope、blocker、active_redlines。



### 分域审计

- `mmflow audit` 是只读分域审计：integrity、lineage、evidence、scientific-bindings、publication、compliance、review、delivery、release-status 各自产生独立状态，聚合不得掩盖子域 ERROR；任何分域都不修改项目。
- P8 对稿件与 Registry 做双向覆盖：稿件中的每个 `\cite` 必须存在 VALID citation，每个已登记 citation 必须被稿件引用；每个 `\includegraphics` 必须对应已登记 Figure，每个已登记 Figure 必须被稿件引用。
- P1–P4 语义检查升级为完整嵌套检查：清点文件唯一且哈希与 artifact 一致、选题候选人一致性、需求 ID 唯一、问题契约合法题型键、划分引用真实 split、冻结计划带时区的冻结时刻且全部划分有效。
- P5 门禁从账本时序证明冻结先于任何最终测试执行：任何 execution 的创建序号早于冻结证据即失败。
