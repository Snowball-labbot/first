from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import (
    atomic_write_bytes,
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
)


def write_gate_report(
    project_root: Path | str,
    gate_id: str,
    sequence: int,
    report: dict[str, Any],
) -> tuple[str, str]:
    root = Path(project_root).resolve()
    directory = root / ".mmflow" / "reports"
    stem = f"{sequence:06d}_{gate_id}"
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    expected_json = json_path.relative_to(root).as_posix()
    expected_markdown = markdown_path.relative_to(root).as_posix()
    if (
        report.get("json_report_path") != expected_json
        or report.get("markdown_report_path") != expected_markdown
    ):
        raise ValueError("gate report paths must be frozen before hashing")
    lines = [
        f"# 门禁报告 {gate_id}",
        "",
        f"门禁结论：{report['status']}",
        "",
        "| 规则 | 状态 | 严重度 | 原因 |",
        "|---|---|---|---|",
    ]
    for check in report["checks"]:
        reason = str(check.get("reason", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {check['rule_id']} | {check['status']} | {check['severity']} | {reason} |"
        )
    lines.append("")
    non_passing = [check for check in report["checks"] if check["status"] != "PASS"]
    if non_passing:
        lines.append("## 失败实体")
        for check in non_passing:
            entities = check.get("failed_entities") or []
            paths = check.get("failed_paths") or []
            evidence = check.get("evidence") or []
            detail: list[str] = []
            if entities:
                detail.append("实体: " + ", ".join(entities))
            if paths:
                detail.append("路径: " + ", ".join(paths))
            if evidence:
                detail.append("证据: " + ", ".join(evidence))
            if detail:
                lines.append(f"- `{check['rule_id']}`：" + "；".join(detail))
        lines.append("")
        lines.append("## 最小修复动作")
        seen_fixes: list[str] = []
        for check in non_passing:
            for fix in check.get("minimum_fix") or []:
                if fix not in seen_fixes:
                    seen_fixes.append(fix)
                    lines.append(f"- {fix}")
        lines.append("")
        lines.append("## 必须重跑阶段")
        scope: list[str] = []
        for check in non_passing:
            for stage in check.get("rerun_scope") or []:
                if stage not in scope:
                    scope.append(stage)
        if scope:
            lines.append("、".join(f"`{stage}`" for stage in scope))
        else:
            lines.append("- 未声明重跑范围，按最上游失败门禁回退")
        lines.append("")
        redlines = [
            check["active_redline"]
            for check in non_passing
            if check.get("active_redline")
        ]
        if redlines:
            lines.append("## 活动红线")
            for redline in sorted(set(redlines)):
                lines.append(f"- `{redline}`")
            lines.append("")
        blocked = [check.get("block") for check in non_passing if check.get("block")]
        if blocked:
            block = blocked[0]
            lines.append("## 阻塞")
            lines.append(f"- 缺失项：{block.get('missing_item')}")
            lines.append(f"- 原因：{block.get('why_required')}")
            lines.append(f"- 已试替代：{block.get('attempted_alternatives')}")
            lines.append(f"- 最小请求：{block.get('minimum_request')}")
            lines.append(f"- 仍有效输出：{block.get('safe_partial_outputs')}")
            lines.append(f"- 恢复命令：`{block.get('resume_command')}`")
            lines.append("")
    lines.extend(
        [
            "## 修复原则",
            "",
            "修复最上游真实原因，创建新尝试并重跑受影响的下游阶段；不得修改报告或降低门槛。",
            "",
        ]
    )
    markdown_bytes = "\n".join(lines).encode("utf-8")
    report["markdown_sha256"] = sha256_bytes(markdown_bytes)
    report["report_sha256"] = sha256_bytes(
        canonical_json_bytes(
            {key: value for key, value in report.items() if key != "report_sha256"}
        )
    )
    atomic_write_bytes(markdown_path, markdown_bytes)
    atomic_write_json(json_path, report)
    return expected_json, expected_markdown
