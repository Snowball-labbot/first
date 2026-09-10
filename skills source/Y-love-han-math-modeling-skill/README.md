# math-modeling-skill · 数学建模自主全流程

以**证据优先（evidence-first）的 mmflow 运行时**为唯一事实来源的数学建模竞赛全流程 Skill。覆盖 CUMCM（国赛）、MCM/ICM（美赛）、GMCM（研赛/华为杯）、MathorCup、APMCM、深圳杯等赛事的完整生命周期：问题形式化 → 数据治理 → 方法选型 → 受控建模执行 → 验证与反证 → 论文渲染 → 独立审查 → 交付打包。

设计立场：**全程强制证据留痕、可复现、fail-closed**。阶段推进必须通过门禁（证据契约 + 语义检查），禁止跳步、禁止无证据推进、禁止把阶段通过解释成获奖事实；所有登记进入哈希链账本，账本不可变。

## 一、工作流：12 阶段状态机

`P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 → P9 → P10 → P11 → COMPLETE`

| 阶段 | 职责 | 关键动作与产出 |
|---|---|---|
| P0 | 策略锁与任务书 | 固定质量策略、问题契约（problem contract）、证据规范；P0 门禁在无证据时必须失败（fail-closed 语义的锚点） |
| P1 | 环境与能力盘点 | 探测 Python/依赖/排版能力并登记能力报告；锁定本次任务的质量画像 |
| P2 | 输入登记 | 登记赛题、数据等输入；由契约生成需求矩阵（要求什么证据、哪些适配器） |
| P3 | 数据与文献治理 | 数据谱系（data lineage）、数据质量报告、文献登记与泄露审计（leakage audit） |
| P4 | 方法选型与计划冻结 | 候选方法与基线协议、验证协议、冻结分析计划（frozen analysis plan） |
| P5 | 受控模型执行 | 数学模型在**隔离运行时**内执行（沙箱、输出闭包、白名单环境），产出结构化结果与自动登记的执行证据 |
| P6 | 验证与反证 | 验证适配器报告（按模型类型）、退化测试、反证报告（counterevidence report） |
| P7 | 响应矩阵与断言 | 逐问题响应矩阵、断言（claim）与支撑证据登记，供论文引用 |
| P8 | 出版物 | LaTeX 渲染、渲染绑定校验、生产图注册（sidecar 契约）、引用审计、xelatex 真实编译出 PDF |
| P9 | 复现 | 对关键受控执行做 `reproduce`，结果按 json_numeric 等策略逐值比对 |
| P10 | 独立审查 | 多角色评审报告、发现（finding）登记与证据化闭环、合规检查（含真实 PDF 页数）、质量评估 |
| P11 | 交付 | 交付清单、隐私扫描、候选包/终包与校验和、`release-status` 程序计算发布标签、`audit` 终核 |

## 二、mmflow CLI（38 个命令）

```text
生命周期   init / begin / next / gate / advance / status / checkpoint / resume / rollback / migrate
登记       register-input / register-artifact / register-result / register-claim /
           register-formula / register-citation / register-figure / register-finding /
           register-evidence / register-split / batch-register
受控执行   run / figures / render-bindings / scan-manuscript / reproduce
审查       review / invalidate / close-finding
交付与发布 scan-privacy / package / release-status / audit
辅助       book / doctor / export-claims / promote-artifact / retire-artifact
```

- `init <project_root> --competition <赛事> --edition <届次> [--quality-profile adaptive]` 创建项目（赛事与届次是用户事实，工具不代填；已含内容的项目拒绝覆盖，中断项目不可原地续跑，应新建目录）。
- `doctor [--probe-write] [--probe-network]` 环境体检。
- 每次变更写入账本事件（哈希链），`status` 展示阶段状态机；`heal_mismatch.py` 是内容失配的唯一规范恢复入口。

## 三、编排器与隔离运行时

- **auto_drive.py**（fail-closed 编排）：`python scripts/auto_drive.py <project_root> <gen_tag> [step ...]`，按缺省序列 p0→…→p11(prep/pack/scan/ev)→finish 推进；任一阶段 gate 非 PASS 立即停止（退出码继承子进程），绝不跳过门禁。要求项目内预置 `autodrive/plan.json`（schema `mmflow-autodrive-plan/v1`）。
- **隔离运行时**：受控程序在沙箱工作目录内运行，输出闭包精确核对——outputs/ 内不得出现未声明文件、outputs/ 外不得有任何写入；环境变量白名单制；快照与报告外置。官方披露为**目录级隔离，不是 OS 级安全沙箱**（详见 `references/isolation-runtime.md`）。
- **复现**：`mmflow reproduce --execution <id>` 按登记的比较策略（sha256 / json_exact / json_numeric / statistical_json）逐值复算并出报告。
- **隐私扫描**：对交付成员逐文件检测绝对路径泄漏等规则，二进制文件同样生效。

## 四、references/：15 份操作手册

`workflow-contract.md`（P0–P11 行为规范、状态、门禁、恢复、退出码语义的唯一规范）、`evidence-registration-cookbook.md`（证据登记配方）、`isolation-runtime.md`（隔离运行时与源树卫生）、`evidence-and-claims.md`、`data-and-literature-governance.md`、`model-selection.md`、`validation-by-model-type.md`（含图像/信号处理与灵敏度管线）、`figure-coverage.md`、`paper-and-visuals.md`、`problem-formalization.md`、`competition-compliance.md`、`review-recovery-and-defense.md`、`extended-competition-playbook.md`、`extended-sprint-protocol.md`、`migration.md`。

## 五、templates/：56 个模板资产（7 类目）

| 类目 | 数量 | 内容 |
|---|---|---|
| analytics | 12 | EDA（stage4_eda）、统计检验、灵敏度分析、收敛扫描、极端测试、交叉验证回测、数据预处理、题型参考实现等 |
| visualization | 21 | 数据概览、分布、热力图、网络图、帕累托、雷达、散点拟合、残差诊断、空间地图、收敛、架构图、模型图等，含公共绘图库与 MATLAB 后端契约 |
| production | 7 | LaTeX 论文主模板（中/英）、模型入口、图形样式、产物契约 |
| publication | 7 | 摘要构建与填充检查、一致性校验、Word 导出（中/英） |
| presentation | 2 | 答辩 PPT 生成、问答卡 |
| quality | 5 | 查重代理、AI 痕迹检查、附录代码闭包检查、特等奖证据模板 |
| examples | 2 | 最小可运行示例 |

模板清单由 `templates/template_manifest.json` 登记，`integrate_templates.py` 负责向项目安全复制（含路径逃逸防护）与清单校验。

## 六、scripts/：运行时与验收工具链

| 工具 | 用途 |
|---|---|
| mmflow.py | 运行时本体（38 个子命令） |
| auto_drive.py | fail-closed 自动编排 |
| validate_skill.py | 23 项全局契约校验（交付卫生 / 模板清单 / 策略 JSON / CLI 契约 / 证据依赖契约 / 隔离披露等），自动清理缓存 |
| integrate_templates.py | 模板清单校验与安全复制 |
| run_tests.py | 5 组 / 41 文件 / 237 个测试函数的验收套件（快照外置 + 源树零改动校验） |
| heal_mismatch.py | 账本内容失配的规范恢复（秩守卫 / 血缘传播） |
| build_release.py / clean_delivery.py / check_template_completion.py | 发布构建 / 交付净化 / 模板完成度检查 |

## 七、使用方法

所有 `mmflow` 命令都需要 `--project <项目目录>`；加 `--json` 可获得机器可读输出。技能设计为**由 AI 代理驱动**，也支持手动 CLI 驱动与自动编排三种用法。

### 方式一：作为 AI 代理技能使用（推荐）

将本仓库克隆到代理的技能目录（如 Claude Code 的 `~/.claude/skills/math-modeling`，或 Codex 的技能目录 `~/.codex/skills/math-modeling`），目录名与 `SKILL.md` 的 `name: math-modeling` 保持一致。之后在对话中直接下达竞赛任务（例如"用数学建模技能完成 2026 年 CUMCM C 题全流程"），代理会：

1. 读取 `SKILL.md` 与对应阶段所需的 `references/` 手册；
2. `mmflow init` 创建项目并逐阶段登记证据、受控执行、过门禁；
3. 在 P8 用模板完成论文渲染与真实编译，P10 组织评审，P11 打包交付并输出发布标签。

代理只负责填写"用户事实"（赛事名称、届次、数据解读与建模决策），所有状态与证据均由 mmflow 运行时裁决。

### 方式二：手动 CLI 驱动（全部命令需 `--project`）

```powershell
$MM = "path/to/math-modeling-skill/scripts/mmflow.py"
$P  = "D:/work/my-contest"          # 项目目录（须为空目录；中断后应新建目录而非复用）

python $MM doctor --probe-write                       # 环境体检
python $MM init --competition CUMCM --edition 2026C --project $P --json

python $MM begin P0 --project $P --json               # 进入阶段（登记策略锁/问题契约/证据规范）
python $MM gate  P0 --project $P --json               # 门禁校验（FAIL 时修复后重跑）
python $MM advance --project $P --json                # 推进到下一阶段（注意：不带阶段参数）

# P1–P10 同型循环：begin → 按手册登记证据/受控执行 → gate → advance
#   P5 模型执行用 run（受控沙箱），P7 用 register-claim/register-evidence，
#   P8 用 render-bindings + run（编译）+ register-figure，P9 用 reproduce，P10 用 review/close-finding

python $MM begin P11 --project $P --json              # 交付：清单/隐私扫描/打包由执行方登记
python $MM scan-privacy --manifest <清单> --output <报告> --project $P --json
python $MM package --candidate --project $P --json    # 候选包 → gate P11 → advance → 终包
python $MM release-status --project $P --json         # 程序计算发布标签
python $MM audit --project $P --json                  # 终核（NOT_READY 项清零后才可发布）
```

### 方式三：auto_drive 自动编排（fail-closed）

```powershell
# 1) 先手动 init（赛事与届次是用户事实，编排器不代填）
python scripts/mmflow.py init --competition CUMCM --edition 2026C --project $P --json

# 2) 在 $P/autodrive/plan.json 预置编排计划（最小骨架）：
# {
#   "schema":  "mmflow-autodrive-plan/v1",
#   "gen_tag": "gen-001",
#   "content": {},                      # 各阶段内容区可留待填充
#   "p11": {                            # 四个交付路径必填
#     "manifest":          "deliverables/delivery_manifest.json",
#     "candidate_package": "deliverables/candidate.zip",
#     "privacy_scan":      "payloads/privacy_scan.json",
#     "final_package":     "deliverables/final.zip"
#   }
# }

# 3) 启动编排（缺省序列 p0→…→p11(prep/pack/scan/ev)→finish）
python scripts/auto_drive.py $P gen-001
```

编排器对每个阶段"需要时 begin → gate，PASS 才 advance"；任何 FAIL/BLOCKED 立即停止且退出码非零——这是有意设计（fail-closed），修复证据后重跑即可。

### 恢复与排障

| 场景 | 办法 |
|---|---|
| 环境可疑 | `mmflow doctor --probe-write --probe-network` |
| 查看状态/下一步提示 | `mmflow status` / `mmflow next` |
| 会话中断后 | 新目录重新 init（账本不可变，不原地续跑）；`export-claims` 可导出既有断言 |
| 账本内容失配 | `scripts/heal_mismatch.py`（唯一规范恢复入口） |
| 测试/校验报源树变脏 | 先跑 `validate_skill.py` 自动清理缓存，再用外部 `--output-root` 复跑 |

## 八、质量与验收状态

- 模板清单：56 模板 / 6 生产类目 + examples / 0 错误
- 全局契约：23 项校验全部 PASS
- 全量测试：237 个测试函数 / 5 组全部 PASS，且源树零改动（`source_unchanged=true`）
- 端到端：P0→P11 在干净项目上真实走完至 `COMPLETE`（含 xelatex 真实编译、复现 PASS、隐私扫描零命中、fail-closed 演示 rc=3），程序计算发布标签 `SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW`
- 提醒：在仓库根目录直接运行脚本会产生 `__pycache__` 等缓存（DELIVERY-HYGIENE 校验会自动清理）；测试输出必须指向外部目录，否则源树卫生校验会按设计报脏

## 九、已知行为语义（避免误判为缺陷）

- 沙箱环境白名单不含 HOME/USERPROFILE/APPDATA 等用户目录变量；需要的工具（如 MiKTeX）应在 run 配置 `environment` 字段声明注入
- 受控运行 outputs/ 内的每个文件都必须在 expected_outputs 声明并配比较策略；LaTeX 的 aux/log/out 副产物同样需要声明
- 证据 `supports` 必须与按类型声明路径抽取的引用精确相等（`given_value` 类型无抽取路径，引用关系经 `content.finding_id` 表达）
- 隐私扫描的绝对路径模式对二进制文件同样生效（如 PNG 元数据中的 URL），交付图应先净化
- 账本只进不退；`gate` 之后不得再登记证据（advance 校验门禁快照新鲜度）

## 十、证据体系与比较策略

### 46 种证据类型

每种证据类型都有独立的 schema 契约与阶段许可矩阵（`scripts/mmflow_core/policies/evidence-v1.json`、`schemas-v1.json`），登记时由运行时校验内容必填项与依赖抽取：

```text
任务与规范   policy_lock, problem_contract, requirement_matrix, capability_report,
            competition_rules, input_inventory, selection_record, quality_profile_selection
数据与文献   data_lineage, data_quality_report, literature_registry, leakage_audit
方法与计划   baseline_protocol, model_candidates, validation_protocol, frozen_analysis_plan,
            candidate_rejection_record
执行与结果   production_execution, structured_results, validation_adapter_report,
            degenerate_test, counterevidence_report
断言与论文   response_matrix, claim_registry, manuscript_source, figure_registry, citation_audit
复现与审查   reproduction_report, review_report, review_findings, compliance_report,
            quality_assessment, paper_depth_review, special_prize_quality_assessment,
            independent_review_provenance
深度记录     theorem_application_record, formula_validity_record, innovation_ablation_record,
            counterintuitive_finding_record, cross_problem_framework_record,
            mechanism_explanation_record, negative_result_record
交付         delivery_manifest, package_checksum, privacy_scan, given_value
```

### 四种比较策略（reproduce 与闭包）

| 策略 | 语义 | 适用 |
|---|---|---|
| `sha256` | 字节级一致 | 源文件、绑定清单、确定性产物 |
| `json_exact` | JSON 结构与值完全一致 | 结构化结果 |
| `json_numeric` | 数值按容差逐值比对 | 数值计算结果（复现首选） |
| `statistical_json` | 统计分布级比对 | 含随机性的结果 |

### 退出码语义（实测口径）

| 退出码 | 含义 | 典型场景 |
|---|---|---|
| 0 | 成功 | 命令通过、门禁 PASS |
| 2 | 配置/契约错误（ConfigError） | 缺必填字段、断言类型非法、策略数不匹配 |
| 3 | 门禁未过（GateFailedError）/ 编排器 fail-closed 停止 | 证据缺失、门禁证据过期 |
| 4 | 完整性错误（IntegrityError） | 哈希不符、依赖不匹配、越界写入 |

## 十一、常见问题（FAQ）

**Q1：为什么 `init` 拒绝覆盖、中断的项目不能原地续跑？**
账本不可变是可复现性的根基：项目状态只进不退，任何“就地修复”都会破坏哈希链的证据效力。中断后请新建目录，用 `export-claims` 导出既有断言作为新任务的登记素材。

**Q2：为什么 `gate` 之后不能继续登记证据？**
`advance` 会校验门禁证据快照的新鲜度——门禁后新增证据意味着“已审计的快照”与“实际状态”不一致（stale）。正确顺序是：登记完该阶段全部证据 → gate → advance。

**Q3：为什么受控运行里 LaTeX/工具报“找不到用户目录”？**
沙箱环境是白名单制（仅系统变量），不透传 HOME/USERPROFILE/APPDATA——这是封闭性设计。需要的工具应在 run 配置的 `environment` 字段声明注入，该声明会随执行存证记录。

**Q4：`release-status` 的标签（如 SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW）是什么意思？**
它是程序按策略与真实证据重算的候选标签，其中 LIMITED_REVIEW 指评审独立性受限（如同代理角色扮演）。标签是质量过程状态的如实反映，不是获奖承诺——Skill 在契约层面禁止任何获奖/名额保证。

**Q5：隐私扫描为什么对 PNG 这类二进制也报“绝对路径”？**
泄漏检测的字节模式对二进制同样生效（如 matplotlib 元数据中的 URL、压缩数据中的随机碰撞）。交付图应在登记前净化元数据并重压缩，并同步 sidecar 哈希。

**Q6：想更换赛题/数据怎么办？**
同一项目内更换上游输入会使已登记证据失配（上游变更语义）。规范做法是新建项目目录重新走流程，旧项目的账本与结论可完整审计追溯。

## License

[MIT](LICENSE) © 2026 Y-love-han
