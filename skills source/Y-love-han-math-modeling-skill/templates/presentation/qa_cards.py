# -*- coding: utf-8 -*-
"""
qa_cards.py — 答辩问答卡片生成器（P11 答辩准备）
用途：从 claim 登记导出的 JSON 生成结构化答辩卡片。每张卡片回答：
      结论是什么 / 证据在哪 / 假设是什么 / 可能被怎么反驳 / 如何回应。
      另附 10 个标准答辩问题骨架，逐个绑定到相关 claim_id。
定位：本脚本只做格式化，不生成任何事实；所有内容逐字来自输入 JSON，
      输入必须由已登记的 claim/result/formula/citation 导出，不得手编数值。

输入 schema: mmflow-defense-cards-input/v1
{
  "schema": "mmflow-defense-cards-input/v1",
  "competition": "CUMCM",
  "claims": [
    {
      "claim_id": "C-01",
      "statement": "核心结论原文（逐字来自 Registry）",
      "supporting_result_ids": ["R-01"],
      "formula_ids": ["F-01"],
      "citation_ids": ["CT-01"],
      "limitations": ["适用限制"]
    }
  ]
}

运行方式：python qa_cards.py --claims claims_export.json --output 答辩问答卡片.md
claims 导出来源映射（优先用 `mmflow export-claims --question Q1 --output claims.json`
生成；手工组装时逐字复制，禁止编造数值）：
  claim_id              <- register-claim 的 claim_id
  statement             <- claim 登记的原始文字（逐字复制）
  supporting_result_ids <- claim supports 中指向 result 的实体 ID
  formula_ids/citation_ids <- claim supports 中对应类型实体 ID
  limitations           <- claim 登记的适用限制字段
退出码：0 成功；2 输入不合法
"""
import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REQUIRED_SCHEMA = "mmflow-defense-cards-input/v1"

# 十个标准答辩问题（唯一规范来源：create_ppt.py 预答备忘也从本表导入，
# 两处不得再各自维护不同措辞的重复清单）。每项：(主题, 问题, 答题思路)
STANDARD_QUESTIONS = [
    ("方法选择依据", "为什么选择该方法而非更简单的基线？基线对比结果在哪里？",
     "从数学结构匹配度、数据特征适配性、计算效率三个角度回答，并引用基线对比的具体数值。"),
    ("创新点辩护", "创新点相对已有方法的增量是什么？消融证据是否支持？",
     "回答'已有方法做不了什么 → 我们做了什么 → 效果提升多少'，引用消融记录。"),
    ("假设质疑", "哪条假设最可能不成立？违反时结论如何变化？",
     "逐一论证假设合理性，引用数据支持；给出假设不成立时的修正方案与结论变化方向。"),
    ("参数辩护", "关键参数取值的数据/文献依据是什么？敏感性如何？",
     "区分数据驱动估计、理论推导、经验值三类来源，并引用灵敏度分析结果。"),
    ("过拟合排除", "划分边界与预处理拟合范围如何防止信息泄漏？",
     "K 折交叉验证 + 留出验证 + 与简单方法对比 + 复杂度惩罚，指出冻结的划分 ID。"),
    ("稳健性", "参数扰动、噪声和退化场景下结论是否保持？",
     "引用 Tornado/Sobol/MC 与极端测试结果，指出最敏感因素和结论不变域。"),
    ("推广性", "结论适用边界是什么？换一个场景还成立吗？",
     "说明模型适用范围（外推边界）、推广条件与迁移注意事项。"),
    ("局限性", "最主要的局限是什么？它对主结论的影响有多大？",
     "诚实陈述 2-3 个具体局限，量化影响程度并给出改进路径。"),
    ("实际价值", "结果对题目背后的决策问题意味着什么？",
     "从决策支持、效率提升、成本降低等角度量化说明。"),
    ("复现性", "第三方按支撑材料能否复现全部数值？环境差异如何处理？",
     "指向复现入口与环境漂移政策，说明 P9 隔离复现结论与允许差异。"),
]


def _fail(message: str) -> "None":
    print(f"❌ {message}")
    sys.exit(2)


def load_claims(path: Path) -> dict:
    if not path.is_file():
        _fail(f"输入文件不存在: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _fail(f"无法读取或解析 JSON: {error}")
    if not isinstance(payload, dict):
        _fail("输入必须是 JSON 对象")
    schema = payload.get("schema")
    if schema != REQUIRED_SCHEMA:
        _fail(f"schema 必须是 {REQUIRED_SCHEMA}，当前为 {schema!r}")
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        _fail("claims 必须是非空数组")
    seen: set = set()
    for index, claim in enumerate(claims):
        where = f"claims[{index}]"
        if not isinstance(claim, dict):
            _fail(f"{where} 必须是对象")
        claim_id = claim.get("claim_id")
        statement = claim.get("statement")
        if not isinstance(claim_id, str) or not claim_id.strip():
            _fail(f"{where}.claim_id 缺失或为空")
        if claim_id in seen:
            _fail(f"{where}.claim_id 重复: {claim_id}")
        seen.add(claim_id)
        if not isinstance(statement, str) or not statement.strip():
            _fail(f"{where}.statement 缺失或为空")
        for field in ("supporting_result_ids", "formula_ids", "citation_ids"):
            value = claim.get(field, [])
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                _fail(f"{where}.{field} 必须是字符串数组")
        limitations = claim.get("limitations", [])
        if not isinstance(limitations, list) or any(not isinstance(v, str) for v in limitations):
            _fail(f"{where}.limitations 必须是字符串数组")
    return payload


def render_card(claim: dict) -> str:
    """单张卡片：全部字段逐字引用输入，不做任何推断或补写。"""
    lines = [
        f"### 卡片 {claim['claim_id']}",
        "",
        f"- **核心结论**：{claim['statement']}",
    ]
    results = claim.get("supporting_result_ids", [])
    formulas = claim.get("formula_ids", [])
    citations = claim.get("citation_ids", [])
    candidates = (
        "结果 " + ", ".join(results) if results else "",
        "公式 " + ", ".join(formulas) if formulas else "",
        "文献 " + ", ".join(citations) if citations else "",
    )
    evidence_parts = [part for part in candidates if part]
    chain = ("；".join(evidence_parts)
             if evidence_parts
             else "（待填写：从 Registry 导出对应实体 ID）")
    lines.append(f"- **证据链**：{chain}")
    lines.append("- **关键假设**：（待填写：列出该结论依赖的模型/数据假设）")
    lines.append("- **可能反例与回应**：（待填写：构造一个推翻场景并给出既有验证的回应）")
    limitations = claim.get("limitations", [])
    lines.append("- **适用限制**：" + ("；".join(limitations) if limitations else "（待填写）"))
    lines.append("- **若被质疑如何修正**：（待填写：降级措辞 / 补充实验 / 收窄适用范围的具体动作）")
    return "\n".join(lines)


# 每题的关键词匹配表：把标准问题映射到语义相关的 claim（statement/
# question_id 命中关键词即关联），替代原先"全量串接"的粗粒度绑定。
# 匹配是启发式辅助；未命中任何 claim 的问题回退为全量列表。
_QUESTION_KEYWORDS = {
    "方法选择依据": ("基线", "对比", "选择", "方法", "模型"),
    "创新点辩护": ("创新", "改进", "新", "消融", "结构"),
    "假设质疑": ("假设", "违反", "松弛", "前提"),
    "参数辩护": ("参数", "取值", "估计", "标定", "敏感性"),
    "过拟合排除": ("划分", "泄漏", "交叉", "验证", "拟合"),
    "稳健性": ("稳健", "扰动", "噪声", "退化", "敏感"),
    "推广性": ("推广", "迁移", "适用", "外推", "泛化"),
    "局限性": ("局限", "限制", "不足", "失败"),
    "实际价值": ("决策", "建议", "价值", "应用", "成本", "收益"),
    "复现性": ("复现", "种子", "环境", "依赖", "随机"),
}


def _related_claims(question_title: str, claims: list) -> str:
    """按关键词把标准问题映射到相关 claim；无命中时回退全量。"""
    keywords = _QUESTION_KEYWORDS.get(question_title, ())
    hits = [
        claim["claim_id"]
        for claim in claims
        if any(
            keyword in str(claim.get("statement", ""))
            or keyword in str(claim.get("question_id", ""))
            for keyword in keywords
        )
    ]
    return ", ".join(hits) if hits else ", ".join(c["claim_id"] for c in claims)


def render(payload: dict) -> str:
    competition = payload.get("competition", "未注明赛事")
    claims = payload["claims"]
    out = [
        "# 答辩问答卡片",
        "",
        f"- 赛事：{competition}",
        f"- 覆盖 claim 数：{len(claims)}（{', '.join(c['claim_id'] for c in claims)}）",
        "- 来源：本文件仅逐字引用 Registry 导出内容；标注“待填写”的字段须在答辩前补齐并登记。",
        "",
        "## 一、逐 claim 卡片",
        "",
    ]
    for claim in claims:
        out.append(render_card(claim))
        out.append("")
    out.append("## 二、标准答辩问题（10 题）")
    out.append("")
    for index, (title, question, hint) in enumerate(STANDARD_QUESTIONS, start=1):
        related = _related_claims(title, claims)
        out.append(f"{index}. **{title}**：{question}")
        out.append(f"   - 关联 claim：{related}")
        out.append(f"   - 回答要点：{hint}")
        out.append("")
    text = "\n".join(out)
    # 防呆：不允许出现占位符以外的未填模板标记
    if re.search(r"\{\{|\}\}", text):
        _fail("内部错误：输出含未渲染占位符")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="答辩问答卡片生成器（P11）")
    parser.add_argument("--claims", required=True, help="claim 导出 JSON（schema mmflow-defense-cards-input/v1）")
    parser.add_argument("--output", required=True, help="输出 Markdown 路径")
    args = parser.parse_args()

    payload = load_claims(Path(args.claims))
    text = render(payload)
    output_path = Path(args.output)
    if output_path.exists():
        _fail(f"目标已存在，拒绝覆盖（新建 attempt 或更换文件名后重试）: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    print(f"✅ 已生成 {output_path}（{len(payload['claims'])} 张卡片 + 10 标准问题骨架）")


if __name__ == "__main__":
    main()
