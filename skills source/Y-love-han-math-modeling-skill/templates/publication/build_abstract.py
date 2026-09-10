# -*- coding: utf-8 -*-
"""
build_abstract.py — 摘要草稿生成器（P7→P8 衔接，presentation-ready）
用途：从 `mmflow export-claims` 导出的 claims JSON 生成中英双语摘要草稿
      Markdown。草稿只做"已登记主张的重新编排"：
      - 中文摘要正文逐字引用 claim 原文（含全部数值），不生成新数字；
      - 英文摘要对每条主张给出占位翻译槽位（不做机器翻译，避免失真）；
      - 背景句、关键词、贡献句等非主张内容显式标记【待填:字段说明】，
        由作者填写后人工核验。
定位：草稿工具，输出不是论文摘要本体；数值一致性由 P8 门禁与
      check_abstract_fill.py、verify_consistency.py 复核。

输入 schema: mmflow-defense-cards-input/v1（与 qa_cards.py 同源）
运行方式：python build_abstract.py --claims claims_export.json --output abstract_draft.md
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

# 主贡献优先级关键词：命中者排前，避免草稿按登记顺序而非贡献顺序编排
_PRIORITY_PATTERN = re.compile(
    r"最优|提升|降低|预测|排名|方案|评估|误差|收敛|增长率|贡献"
)

NUMBER_PATTERN = re.compile(
    r"[-+]?\d+(?:\.\d+)?(?:\s*[×x*]\s*10\s*[-+]?\d+)?(?:%|‰)?"
)


def _fail(message: str) -> None:
    print(f"error: {message}")
    sys.exit(2)


def _question_sort_key(claim: dict) -> tuple:
    qid = str(claim.get("question_id") or "Q0")
    match = re.search(r"(\d+)", qid)
    return (0, int(match.group(1))) if match else (1, qid)


def extract_numbers(statement: str) -> list[str]:
    """草稿自检：列出该主张承载的全部数值，供作者逐字核对来源。"""
    seen = []
    for item in NUMBER_PATTERN.findall(statement):
        normalized = item.strip()
        if normalized not in seen:
            seen.append(normalized)
    return seen


def build_draft(payload: dict) -> str:
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        _fail("claims export must contain a non-empty 'claims' list")
    competition = payload.get("competition") or "competition"
    edition = payload.get("edition") or "current edition"
    ordered = sorted(
        claims,
        key=lambda claim: (
            _question_sort_key(claim),
            0 if _PRIORITY_PATTERN.search(str(claim.get("statement", ""))) else 1,
        ),
    )
    lines: list[str] = []
    lines.append("# 摘要草稿（数值逐字取自 export-claims，未经人工核验不得提交）")
    lines.append("")
    lines.append(f"> 来源：{competition} {edition}；生成工具 build_abstract.py；"
                 f"claims 共 {len(claims)} 条。")
    lines.append("")
    lines.append("## 中文摘要草稿")
    lines.append("")
    lines.append("【待填:题目背景与建模动机一句（不得出现本文未证明的形容词）】")
    lines.append("")
    lines.append("针对问题，本文【待填:总体方法路线一句】。")
    lines.append("")
    for claim in ordered:
        statement = str(claim.get("statement", "")).strip()
        claim_id = str(claim.get("claim_id", "?"))
        question = str(claim.get("question_id") or "通用")
        numbers = extract_numbers(statement)
        lines.append(f"- **{question}**（{claim_id}）：{statement}")
        if numbers:
            lines.append(f"  - 数值清单（须与 Registry 一致）：{ '、'.join(numbers) }")
        limitations = claim.get("limitations") or []
        if limitations:
            lines.append(f"  - 适用限制：{'；'.join(str(item) for item in limitations)}")
    lines.append("")
    lines.append("【待填:验证证据概括一句（引用 P6 反证/灵敏度/复现结论）】")
    lines.append("")
    lines.append("【待填:实际含义与建议一句】")
    lines.append("")
    lines.append("**关键词**：【待填:关键词3至5个，分号分隔】")
    lines.append("")
    lines.append("## English Summary Draft")
    lines.append("")
    lines.append("【待填:one-sentence background and motivation】")
    lines.append("")
    lines.append("For each registered claim, render the following points in formal English "
                 "(numbers must be copied verbatim from the claim statement):")
    lines.append("")
    for claim in ordered:
        claim_id = str(claim.get("claim_id", "?"))
        question = str(claim.get("question_id") or "general")
        statement = str(claim.get("statement", "")).strip()
        lines.append(f"- ({claim_id}, {question}) 【待填:English rendering】 "
                     f"Source claim (verbatim): {statement}")
    lines.append("")
    lines.append("【待填:validation evidence summary sentence】")
    lines.append("")
    lines.append("**Keywords**: 【待填:3 to 5 keywords, semicolon separated】")
    lines.append("")
    lines.append("## 自检清单")
    lines.append("- [ ] 每条数值已与 claim/result 登记值逐字核对")
    lines.append("- [ ] 主张强度与 Registry claim_strength 一致，无越界表述")
    lines.append("- [ ] 全部【待填】槽位已由作者填写并删除标记")
    lines.append("- [ ] 中文摘要篇幅符合当届规则（用 check_abstract_fill.py 复核）")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build bilingual abstract draft from export-claims JSON")
    parser.add_argument("--claims", required=True, help="mmflow export-claims output JSON")
    parser.add_argument("--output", required=True, help="draft markdown (must not exist)")
    args = parser.parse_args(argv)

    claims_path = Path(args.claims)
    if not claims_path.is_file():
        _fail(f"claims export not found: {claims_path}")
    payload = json.loads(claims_path.read_text(encoding="utf-8"))
    if payload.get("schema") != REQUIRED_SCHEMA:
        _fail(f"claims export schema must be {REQUIRED_SCHEMA}")
    draft = build_draft(payload)
    output = Path(args.output)
    if output.exists():
        _fail(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(draft, encoding="utf-8")
    claims_count = len(payload.get("claims", []))
    print(json.dumps({"status": "OK", "claims": claims_count,
                      "output": str(output),
                      "note": "draft only; numbers verbatim from claims; fill marked slots manually"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
