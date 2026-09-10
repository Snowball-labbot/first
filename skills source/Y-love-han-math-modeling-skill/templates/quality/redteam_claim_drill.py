# -*- coding: utf-8 -*-
"""
redteam_claim_drill.py — P7 收尾红队预审（对抗审查前移）
用途：P7 结束、进入 P8 写作之前，对每条已登记 VALID claim 生成一份
      攻击面清单。按主张内容自动匹配最可能被 P10 审查角色攻击的类别
      （最优性无证书、因果越界、稳健性缺失、数据泄漏、外推越界、
      假设不可识别），逐条给出攻击问题与"既有验证覆盖"填写列；
      高频 CRITICAL/MAJOR 来源在写作前消灭，显著降低后期回退成本。
定位：风险清单工具。攻击类别只按关键词匹配触发，不产生任何新事实；
      "既有验证覆盖/缺口处置"两列必须由作者填写（填已有验证的
      evidence/result ID，或标记缺口并决定回 P6 补验或降级主张强度）。
      预审记录写入决策摘要，不产生新的必需证据类型。

输入 schema: mmflow-defense-cards-input/v1（`mmflow export-claims` 同源）
运行方式：python redteam_claim_drill.py --claims claims_export.json \
              --output-md attack_surface.md --output-json attack_surface.json
退出码：0 成功；2 输入不合法
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REQUIRED_SCHEMA = "mmflow-defense-cards-input/v1"

# 攻击类别：(类别名, 触发关键词, 攻击问题, P10 对应审查角色)
ATTACK_CATEGORIES = [
    ("最优性证书", r"最优|最短|最小成本|最大收益|optimal",
     "宣称的最优性是否有证书（精确解的界/gap、启发式的下界对照与多种子稳定性）？"
     "可行解与全局最优的区分在哪里写明？", "数学数值审查"),
    ("因果识别", r"因果|导致|归因|影响机制|causal",
     "因果主张的 estimand、识别假设与敏感性分析在哪里？"
     "仅有关联证据时是否已降级为关联表述？", "数学数值审查"),
    ("稳健性与扰动", r"稳定|稳健|显著|可靠|鲁棒",
     "参数扰动、噪声注入与退化场景下结论是否保持？"
     "最敏感因素与结论不变域是否量化？", "数据统计审查"),
    ("数据泄漏", r"预测|拟合|训练|准确率|R2|R²",
     "划分边界与预处理拟合范围是否隔离？同一主体/时段是否跨集合？"
     "指标方向与题目要求是否一致？", "数据统计审查"),
    ("外推边界", r"预测|未来|外推|推广|2030|趋势",
     "外推是否超出数据支持范围？外推边界在问题契约与论文中如何标注？"
     "超出部分是否标记为情景假设？", "复现审查"),
    ("可识别性", r"假设|参数|机理|系数",
     "关键参数是否有数据/文献支持？参数同时调节是否会让任意解拟合训练数据？"
     "模型退化情形（极端参数、零模型）行为是否检查？", "论文合规审查"),
]
FALLBACK_CATEGORY = ("证据链完整性", None,
                     "每项数值是否可由 result_id 回溯？图与源数据是否同 execution？",
                     "论文合规审查")


def classify(statement: str) -> list[dict]:
    matched = []
    for name, pattern, question, role in ATTACK_CATEGORIES:
        if pattern and re.search(pattern, statement, flags=re.IGNORECASE):
            matched.append({"category": name, "attack": question, "role": role})
    if not matched:
        name, _pattern, question, role = FALLBACK_CATEGORY
        matched.append({"category": name, "attack": question, "role": role})
    return matched


def drill(claims: list[dict]) -> list[dict]:
    surface = []
    for claim in claims:
        statement = str(claim.get("statement", "")).strip()
        claim_id = str(claim.get("claim_id", "?"))
        question = str(claim.get("question_id") or "通用")
        supports = claim.get("supporting_result_ids") or []
        attacks = classify(statement)
        priority = "HIGH" if len(attacks) >= 2 else "NORMAL"
        surface.append({
            "claim_id": claim_id,
            "question_id": question,
            "statement": statement,
            "supporting_result_ids": supports,
            "risk_priority": priority,
            "attacks": [
                {
                    "category": item["category"],
                    "attack_question": item["attack"],
                    "reviewer_role": item["role"],
                    "existing_coverage": "【待填:既有验证覆盖（evidence/result ID）或缺口】",
                    "disposition": "【待填:缺口处置——回 P6 补验 / 降级主张强度 / 保留限制】",
                }
                for item in attacks
            ],
        })
    return surface


def render_markdown(surface: list[dict], meta: dict) -> str:
    high = [item for item in surface if item["risk_priority"] == "HIGH"]
    lines = [
        "# P7 红队预审攻击面清单",
        "",
        f"> 来源：{meta.get('competition') or 'competition'} "
        f"{meta.get('edition') or ''}；claims 共 {len(surface)} 条，"
        f"多类别命中（HIGH）{len(high)} 条。",
        "> 使用方式：逐条填写 `既有验证覆盖`（指向已登记的验证证据 ID），",
        "> 或在 `缺口处置` 决定回 P6 补验 / 降级主张强度；预审记录写入决策摘要。",
        "",
    ]
    for item in surface:
        lines.append(f"## {item['claim_id']}（{item['question_id']}，"
                     f"风险 {item['risk_priority']}）")
        lines.append("")
        lines.append(f"**主张原文**：{item['statement']}")
        lines.append("")
        if item["supporting_result_ids"]:
            lines.append(f"**支撑结果**：{', '.join(item['supporting_result_ids'])}")
            lines.append("")
        for index, attack in enumerate(item["attacks"], start=1):
            lines.append(f"### 攻击 {index}：{attack['category']}"
                         f"（{attack['reviewer_role']} 视角）")
            lines.append("")
            lines.append(attack["attack_question"])
            lines.append("")
            lines.append(f"- 既有验证覆盖：{attack['existing_coverage']}")
            lines.append(f"- 缺口处置：{attack['disposition']}")
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Red-team attack surface checklist for registered claims")
    parser.add_argument("--claims", required=True, help="mmflow export-claims output JSON")
    parser.add_argument("--output-md", default=None, help="markdown checklist output (must not exist)")
    parser.add_argument("--output-json", default=None, help="structured checklist output (must not exist)")
    args = parser.parse_args(argv)
    if not args.output_md and not args.output_json:
        print("error: provide --output-md and/or --output-json")
        return 2

    claims_path = Path(args.claims)
    if not claims_path.is_file():
        print(f"error: claims export not found: {claims_path}")
        return 2
    payload = json.loads(claims_path.read_text(encoding="utf-8"))
    if payload.get("schema") != REQUIRED_SCHEMA:
        print(f"error: claims export schema must be {REQUIRED_SCHEMA}")
        return 2
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        print("error: claims list is empty")
        return 2
    surface = drill(claims)
    for suffix, text in (
        (args.output_md, render_markdown(surface, payload)),
        (args.output_json, json.dumps(
            {"schema": "mmflow-redteam-surface/v1", "surface": surface},
            ensure_ascii=False, indent=2) + "\n"),
    ):
        if not suffix:
            continue
        output = Path(suffix)
        if output.exists():
            print(f"error: output already exists: {output}")
            return 2
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    high_count = sum(1 for item in surface if item["risk_priority"] == "HIGH")
    print(json.dumps({"status": "OK", "claims": len(surface),
                      "high_priority": high_count,
                      "note": "fill existing_coverage/disposition columns; "
                              "record the drill in the decision summary"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
