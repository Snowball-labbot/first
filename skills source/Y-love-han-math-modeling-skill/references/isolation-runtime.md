# 隔离运行与发布卫生规范

## 本文件负责

本文件规定测试、模板校验、交付构建和受控 execution 如何在 Skill 源树外运行，并规定源树前后 manifest、缓存重定向、失败诊断、短路径执行和运行区清理。

## 本文件不负责

目录隔离用于可复现和防止源树污染，不是操作系统级安全沙箱；它不能保证阻止网络访问、任意子进程或主机文件系统逃逸。需要主机级安全边界时，必须由用户提供容器、虚拟机或受限账户。

## 测试入口

使用 `python -B scripts/run_tests.py --unit <node>`、`--quick` 或 `--full`。入口把 Skill 复制到外部快照，禁用或重定向 Python、pytest、mypy、ruff 和临时目录缓存，并输出分组进度、返回码、耗时、源树差异、污染清单、失败运行区和复现命令。quick 套件递归调用自身时会显式标记子进程并跳过递归包装测试，但不跳过其他契约测试。

`--full` 会按稳定边界拆成 `core`、`workflow`、`runner`、`delivery` 和 `figures-docs` 五组；可用 `--group <name>` 只运行其中一组。命名分组只改变执行批次和进度记录，不改变 pytest 目标、断言或门禁。每个分组报告都保留完整目标列表、耗时、返回码和可直接复制的复现命令，因此重量级分组可以单独延长超时复核，避免把多个长任务误判为整体超时。

## 路径与清理

报告可以写入用户指定的外部目录；子进程 cwd 使用系统临时目录中的短路径，避免 Windows 深层路径 `WinError 267`。成功运行删除外部 execution workspace，失败则保留最小诊断。生产 Runner 在 START、FINISH 或 artifact 注册异常时也必须清理短期 workspace；逻辑 evidence 仍保留在项目 `runs/<run_id>/attempts/` 中。

## 卫生判定

源树中已有的 `__pycache__`、`.pytest_cache`、`.mypy_cache`、`.ruff_cache`、`.mmflow`、`.git`、`.pyc`、`.pyo`、`.tmp`、`.bak`、`.swp` 和 `.swo` 必须在交付校验中报告为失败。隔离测试不会把预存污染伪装为新污染；最终交付前应精确清理已核对的条目，再通过 validator 和 ZIP 安全检查。

## 工具链边界

受控执行（execution 闭包、超时终止与输出登记）仅覆盖 Python 程序。MATLAB、LINGO、SPSS、Excel 等其他工具的运行以外部 artifact 加完整操作说明（命令/公式/宏）形式登记，不产生 execution 级证明；论文附录按「附录中非 Python 工具呈现」规范给出可复算细节，并在交付说明中如实标注该部分复现证据弱于 Python 部分。

## run 命令沙箱模型与 config 格式

`run` 命令在 `.mmflow/runs/<run_id>/attempts/<attempt_id>/sandbox/` 创建隔离目录执行程序，并自动创建 execution 实体和 REGISTRY_RECORDED 事件。程序在沙箱 cwd 中运行，因此**相对路径仅对通过 `source_artifact_ids` 映射到沙箱内的文件有效**；输出文件也必须写入沙箱内由 `expected_outputs` 声明的相对路径。

### run config 完整格式

```json
{
  "intent": "求解本题各问（示例：替换为实际意图描述）",
  "expected_outputs": ["results/solve_results.json"],
  "comparison_policies": {
    "results/solve_results.json": {
      "mode": "json_numeric",
      "absolute_tolerance": 0.01,
      "relative_tolerance": 0.01
    }
  },
  "timeout_seconds": 600,
  "source_artifact_ids": [],
  "dataset_split_ids": [],
  "random_protocol": {"seed": 42}
}
```

**random_protocol 与比较策略的配对**：确定性程序用单种子
`{"seed": 42}` + `json_numeric` 即可；随机算法、GPU 训练或多种子协议改用
`{"seeds": [17, 42, 2026], "aggregation": "mean_std"}`（字段为示例形态，
以 P4 冻结的 validation_protocol 登记为准），并把输出改为统计摘要
（均值/标准差/置信区间），comparison_policies 相应使用 `statistical_json`
模式——多种子协议与单种子容差不可混用，详见
`references/validation-by-model-type.md` 随机仿真节。

**comparison_policies 格式**：`dict[str, dict[str, Any]]`——键为逻辑路径（须 ∈ expected_outputs），值为含以下键的 dict：

| mode | 必填额外键 | 说明 |
|---|---|---|
| sha256 | （无额外） | 文件字节哈希完全一致 |
| json_exact | （无额外） | JSON 结构+值精确匹配 |
| json_numeric | absolute_tolerance, relative_tolerance | JSON 数值容差匹配 |
| statistical_json | absolute_tolerance, relative_tolerance | 统计容差匹配 |

**source_artifact_ids**：列出需要在沙箱中可访问的 artifact ID；runner 将这些文件的副本放入沙箱。

### 链式注册顺序（run 命令自动处理的实体）

`run` 成功后自动注册：execution 实体 + 输出文件 artifact + REGISTRY_RECORDED 事件。此后即可引用 execution_id 和 result_id 登记 P5 的 evidence：

```
1. register-artifact (代码文件)
2. run --config ... → 自动创建 execution + output artifact
3. register-evidence(production_execution, content.execution_ids=[<返回的 exec_id>], supports=[exec_id])
4. register-evidence(structured_results, content.result_ids=[...], supports=[...])
```
