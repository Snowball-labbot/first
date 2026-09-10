# v1 到 v2 迁移规范

## 本文件负责

本文件规定 v1 项目的只读计划、兼容性阻断、外部输出目录、备份定位、哈希报告、原子 staging、完整 schema/血缘验证和重新验证状态。

## 本文件不负责

迁移不会推断缺失字段、补造证据、静默丢弃未知字段或把 v1 的 `COMPLETE` 当作 v2 的 `COMPLETE`。迁移成功只表示生成了可加载的 v2 候选项目，不表示科学结果已经重新验证。

## 两阶段流程

`migrate --plan`/`--dry-run` 只读扫描契约、Registry、账本和需要重新验证的 evidence，并报告输入树哈希、映射和阻断项。`migrate --apply --output <new_dir>` 要求输出目录在源项目外且不存在；先复制到 staging，保留 v1 `.mmflow` 备份，更新契约版本和新 `run_id`，重建干净账本，执行加载与完整性检查，通过后再原子改名。任一步骤失败都删除 staging，不改变 v1 源项目。

## 状态与报告

迁移后的契约必须带 `migration_status: REVALIDATION_REQUIRED` 和 `migrated_from_run_id`。报告记录 `input_sha256`、`output_sha256`、备份定位、字段映射、人工待决项、原子性和 `v1_complete_mapping: revalidation_required`。旧 Registry 记录只能作为待核验历史，不能直接满足 v2 production gate。

## 迁移后各阶段证据的复用与重登边界

迁移把旧产物降级为"带哈希的外部输入"，逐阶段处置如下：

| 阶段 | 可直接复用（作为输入重新读取核验） | 必须在新 run 重新登记 |
|---|---|---|
| P0 | 官方规则快照文件（按新 competition_rules 配方重新登记） | capability_report、competition_rules、policy_lock（全部） |
| P1–P2 | 题目/附件原文件、需求清单草稿 | input_inventory、selection_record、requirement_matrix、problem_contract |
| P3 | 原始数据只读副本、清洗脚本 | data_lineage、data_quality_report、literature_registry、leakage_audit、split 实体 |
| P4 | 候选模型说明文本 | baseline_protocol、model_candidates、validation_protocol、frozen_analysis_plan（冻结时点必须晚于迁移） |
| P5–P9 | 源代码、配置、历史结果 JSON（作参考对照） | production_execution、structured_results 及全部验证证据——production 结果必须在迁移后从空 attempt 重跑 |
| P10 | 历史 finding 清单（作审查提示） | review_findings、compliance_report、quality_assessment |
| P11 | 支撑材料源文件 | delivery_manifest、package_checksum、privacy_scan |

判定口径：**凡进入论文或交付包的主张链（execution→result→claim→figure）一律重跑重登**；纯输入侧材料在按新契约登记并核验哈希后复用。迁移后首次 `release-status` 至多为 `REPRODUCIBLE` 路径上的中间态，`QUALITY_REVIEW_READY` 及以上标签必须由新 run 的完整门禁产生。

## 失败与重试边界

- `--apply` 在 staging 校验失败时自动删除 staging 并保持 v1 源项目不变；可修复阻断项（缺失字段映射、路径越界）后对同一输出目录名重试。
- 输出目录已存在时拒绝执行（不覆盖）；换名重试或在确认废弃后手工清理旧候选目录。
- 迁移中断（进程被杀）：staging 目录残留但不影响源项目；重试前先手工删除残留 staging。v1 `.mmflow` 备份仅在 apply 成功提交后写入报告引用，任何时刻不得回写 v1 源项目。
