# 证据登记操作手册：P0–P11 载荷配方与链式顺序

## 本文件负责

本文件是证据登记的唯一操作手册：各阶段门禁必需证据集合、每种证据类型的
逐字段载荷配方、登记时机与链式注册顺序、代际纪律与程序化自省命令路由。
它把分散在各阶段规范中的"登记动作"收敛为一处，供登记前逐行自检，把
stage_epoch 重建压到最少。机器可读同源入口：`mmflow schema`、
`mmflow adapters`、`mmflow cookbook [--stage Pn]`——三者与策略文件
（evidence-v1、schemas-v1、stages-v1）由同一程序加载，本手册与之漂移时以
程序输出为准并修复本手册。

## 本文件不负责

本文件不定义阶段状态、门禁判定、失效传播与退出码（见 workflow-contract.md），
不定义各证据类型的语义边界与审查要求（见对应阶段规范），不替 models 选择
或验证方法做专业判断；也不接受用本手册的文本登记替代 `register-*` 命令的
程序校验——凡本手册与命令实际校验冲突，以命令报错为准。

## 通用登记规则

1. 唯一入口是 `python <skill-root>/scripts/mmflow.py register-<kind> --file <payload.json>`
   （kind ∈ artifact/result/claim/formula/citation/figure/finding/evidence/split；
   输入类用 `register-input --id --type --path`）。批量用
   `batch-register --file <entries.json>`，顶层为 `{entries: [{kind, payload}]}`，
   单条失败记为 ERROR 行，不中断其余条目。
2. 载荷中 `run_id` 可省略（程序注入当前 run）；`created_stage`、`stage_epoch`、
   `created_ledger_sequence` 由程序写入，不得手填。entity_id 全局唯一；
   同一 ID 重复登记被拒绝，状态修订走 `revise` 语义（新版本号），禁止覆盖。
3. 登记前先用只读自省自检（把 epoch 重建压到最少）：
   - `mmflow schema [--evidence-type T] --json`：输出该证据类型 content 必填键、
     依赖提取路径与实测字段注记；
   - `mmflow adapters --json`：全部合法 trait/claim_type/model_family 适配器名；
   - `mmflow next --json`：当前阶段缺失证据与无效实体清单。
4. evidence 载荷的 `supports` 必须与 content 中依赖提取路径实际引用的实体 ID
   完全一致（程序双向核对，缺一或多一都拒绝）。
5. 手工登记禁入 execution：execution 只能由 `run` 命令经 START/FINISH
   受控流产生；`register-execution` 不存在，任何"替 execution 造记录"的
   尝试都会被程序拒绝。
6. artifact_class 一经登记不可变（demo/exploratory/fixture/external/unattested
   不得升为 production）；生产结果必须在冻结后从新 attempt 以 `run` 重新执行。

## 代际纪律（跨 epoch 重生成不卡顿的关键动作）

- 上游根因变化 → 用 `retire-artifact --id <entity_id> --reason ...` 把上一代
  固定路径制品 STALE 并沿血缘传播（**不**自动回退阶段）；返回
  `suggested_rollback_stage`，由调用方显式 `rollback`。
- 需要完整失效+回退时用 `mmflow invalidate --id <entity_id> --reason ...`
  （单事务内构建后代集、计算最早回退阶段并执行）。
- 内容已漂移（monotonic IntegrityError）时用维护入口
  `scripts/heal_mismatch.py --project <root> [artifact_id ...]` 做秩守卫失效
  并回退最早受影响阶段。
- 失效后代重登记时保持 entity 语义一致；代际记录（旧 STALE + 新 VALID）
  都是账本事实，禁止删除或改写旧代。
- 回退后重新 begin 的阶段 epoch 递增：只登记**当前 epoch** 的证据，
  登记前跑 `next` 确认缺失清单，避免把新证据登记进旧 epoch 再重建。

## 链式注册顺序（每个阶段的通用序）

```
1. register-input            题目/规则/数据/文献输入（哈希+来源）
2. （数据处理后）register-artifact + register-split
3. run --config ...          受控执行 → 自动创建 execution + 输出 artifact
4. register-result           结构化结果（引用 execution_id 与 split）
5. register-formula / register-figure（图先经 figures plan 规划）
6. register-claim            主张（supports 指向 result/formula/citation）
7. register-citation         文献（被支撑 claim 双向可定位）
8. register-evidence         阶段必需证据（见下表；supports=content 实际引用）
9. gate <stage> → advance
```

## 各阶段必需证据与载荷配方

下表 evidence 列是 evidence-v1.json `stage_requirements` 的原文；每行的
content 键清单是该证据类型在 schemas-v1.json 中的必填契约。深度证据类型
（右下角带 ▲）另有公共键要求，见后节。

### P0 启动与规则核验

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| capability_report | checked_at, capabilities, limitations | 直接消费 `doctor --json` 输出；缺失能力写入 limitations |
| competition_rules | competition, edition, official_sources, rule_snapshots, requirements, verification_status | official_sources/rule_snapshots 每项含 artifact_id 或 citation_id（依赖提取路径）；未核实的冲突登记为 verification_status 红线 |
| policy_lock | policy_sha256, files | 程序生成；不手编 |

### P1 材料清点与选题

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| input_inventory | files, critical_missing | files[].artifact_id 逐项指向已登记 input artifact；未读取内容不得登记为已读 |
| selection_record | applicable, candidates, selected, rationale | 多题赛事逐候选比较；单题登记 applicable=false 及理由 |

### P2 赛题形式化

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| requirement_matrix | requirements | 12 字段需求矩阵；requirement_id 唯一 |
| problem_contract | problems | 每问任务/输入/输出/变量/约束/单位/claim 类型/外推边界；traits 用合法适配器名 |

### P3 数据与证据工程

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| data_lineage | sources, transforms, splits | sources[].artifact_id、transforms[].artifact_id、splits[] 指向真实 split 实体 |
| data_quality_report | datasets, issues, decisions | datasets[].artifact_id；质量分级与处理决策逐项可追溯 |
| literature_registry | citation_ids, unresolved | citation_ids[] 全部指向已登记 citation |
| leakage_audit | checks, status | 8 项检查逐项给结论；status 与 checks 一致 |

### P4 模型与实验设计

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| baseline_protocol | baselines, metrics | 与主模型共享边界/split/指标 |
| model_candidates | candidates, selection_rule | 词典序选择规则；候选九字段齐备 |
| validation_protocol | adapters, metrics, stopping_rules, comparison_policies | adapters 用 `mmflow adapters` 合法名 |
| frozen_analysis_plan | frozen_at, viewed_final_test, primary_metrics, split_ids | frozen_at 带时区 ISO；viewed_final_test=false；split_ids[] 指向真实 split |
| quality_profile_selection | profile, selected_at, rationale, frozen_with_analysis_plan | 启用非默认 profile 时登记适用理由与未启用项 |

### P5 基线、建模与求解

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| production_execution | execution_ids | execution_ids[] 全部来自 `run`（exit 0、production 类）；跨阶段继承自 P5，P9 不得重复登记 |
| structured_results | result_ids | result_ids[] 指向已登记 result；论文数字全部经 result_id |
| theorem_application_record ▲ | 公共键 + theorems | 定理条件逐项核对；不满足降级 |

### P6 验证、稳健性与反证

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| validation_adapter_report | reports | 按 Problem Contract 的 traits/claim_types/model_families 逐适配器出具 |
| degenerate_test | tests, status | 边界/退化/零模型场景与结论 |
| counterevidence_report | tests, unsupported_claims, status | unsupported_claims[] 触发主张降级或删除 |
| problem_contract | problems | 跨阶段继承自 P2（P2 PASSED 且未失效时免重登） |
| candidate_rejection_record ▲ / innovation_ablation_record ▲ / counterintuitive_finding_record ▲ / cross_problem_framework_record ▲ / mechanism_explanation_record ▲ / negative_result_record ▲ | 公共键 + candidates/innovations/findings/framework+problem_links/explanations/results | 按启用的 profile 与实际信息增量登记，不机械复制 |

### P7 结论综合与主张登记

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| response_matrix | rows | rows[] 每项 requirement_id + claim_ids + manuscript_target（论文锚点如 sec:q1；缺失即 P7 语义 FAIL） |
| claim_registry | claim_ids | claim_ids[] 指向已登记 claim；核心结论 claim_id 齐备 |

### P8 论文与图表生成

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| manuscript_source | source_artifact_id, rendered_artifact_id, binding_manifest_artifact_id, source_closure, binding_count, unbound_number_count | 先 render-bindings 后登记；source_closure[].artifact_id 覆盖编译闭包 |
| figure_registry | figure_ids | figure_ids[] 指向已登记 figure；生产图 11 项契约字段齐备 |
| citation_audit | citation_ids, unresolved | unresolved 清空或降级相关主张 |
| paper_depth_review ▲ | 公共键 + manuscript_sections | 深度审查记录；不适用给结构化理由 |

### P9 隔离复现

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| reproduction_report | reports | reports[] 每项 original_execution_id + reproduction_execution_id（依赖提取路径）+ 比较模式与结论 |
| production_execution | execution_ids | 跨阶段继承自 P5；P9 不得重复登记第二条该类型 |

### P10 对抗审查与合规审查

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| review_findings | finding_ids, open_by_severity, independent_review, roles | roles[].evidence_ids 各指向恰好一条 VALID review_report；其 created_ledger_sequence 晚于最后一次 P8 GATE_RECORDED |
| compliance_report | checks, status, official_rule_citations, requirement_checks | 引用当届规则结构化条目 |
| quality_assessment | dimensions, total, contribution_claim_ids, review_independence | dimensions[].id 取自 quality_dimensions 键集且 maximum 精确相等；model_correctness 与 validation_counterevidence 两维 earned/max≥0.9，其余 ≥0.8；total=Σearned 且 ≥90 |
| review_report | role, scope, checks, finding_ids, reviewer_mode | 每审查角色一条；只审已存在稿件/结果 |
| independent_review_provenance | reviewers, limitations | reviewers[].execution_id / input_artifact_ids[] / output_artifact_ids[] |
| special_prize_quality_assessment ▲ | 公共键 + level, program_facts, experiment_supported, professional_judgments, cannot_guarantee, criterion_results, total | 仅在 special-prize profile 下需要；评分由 policy 重算 |

### P11 打包与答辩材料

| 证据类型 | content 必填键 | 配方要点 |
|---|---|---|
| delivery_manifest | files, excluded_prefixes | 另需 distribution_licenses 列表与实测 smoke_command 参数（见 schema 注记）；files[].artifact_id 指向交付成员 |
| package_checksum | package_artifact_id, sha256, archive_test | 打包后登记；archive_test 记录新目录解压核验结论 |
| privacy_scan | checker_version, status, files | 允许 P10/P11 登记；与 scan-privacy 报告同源 |

## 深度证据公共键（▲ 类型）

theorem_application_record、candidate_rejection_record、formula_validity_record、
innovation_ablation_record、counterintuitive_finding_record、
cross_problem_framework_record、mechanism_explanation_record、
negative_result_record、paper_depth_review、special_prize_quality_assessment
共用以下键（formula_validity_record 的专有键为 formulas；P4 阶段允许登记
formula_validity_record / candidate_rejection_record）：

- `applicability`：applied / not_applicable 二值；
- `not_applicable_reason` + `not_applicable_detail`：判定为不适用时的结构化
  理由（判定依据、对质量判断的影响、是否需要替代验证），不能只写一句；
- `source_entity_ids[]`、`supported_claim_ids[]`、`alternative_evidence_ids[]`：
  内容中实际引用的实体必须与 `supports` 完全一致（依赖提取路径核对）；
  被引用实体失效时本记录一并失效；
- `problem_ids[]`、`method`、`checks`、`limitations`、`reviewer`。

## 阶段允许矩阵与跨阶段继承

每种证据类型允许登记的阶段以 evidence-v1.json `evidence_stage_matrix` 为准
（46 类全量、逐类型）。要点：

- 跨阶段继承仅三类：competition_rules（P0）、problem_contract（P2）、
  production_execution（P5）；继承条件是来源阶段当前 PASSED 且实体未失效。
- 在矩阵未开放的阶段登记会被程序拒绝；需要补证据时先 `next` 查看最小
  重跑范围，由回退而非"换个阶段登记"解决。

## 登记失败的最小诊断序

1. 报错 `dependency mismatch`：supports 与 content 引用不一致——重跑
   `mmflow schema --evidence-type T` 对齐提取路径。
2. 报错 `entity already exists`：改状态走 revise 语义（新版本），换代走
   `retire-artifact`；不改旧实体。
3. 报错 stage/epoch 不符：该证据属于别的阶段或旧 epoch——按 `next` 的
   最小重跑范围回退后重登。
4. 报错 artifact 哈希/路径：文件须在项目内、内容与登记哈希一致；漂移时走
   `heal_mismatch.py`。
