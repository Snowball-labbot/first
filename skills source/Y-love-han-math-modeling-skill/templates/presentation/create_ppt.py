# -*- coding: utf-8 -*-
"""
create_ppt.py — 答辩 PPT 自动生成脚本
用途：阶段 11 答辩准备——基于标准结构骨架生成答辩 PPT；
      可选传入 `mmflow export-claims` 导出的 JSON 自动填充
      各问结论页（数字与结论全部来自 Registry，不手抄）。
依赖：python-pptx（pip install python-pptx；未安装时自动降级为文本大纲）
运行方式：
    python create_ppt.py --title "标题" --output 答辩PPT.pptx
    python create_ppt.py --claims claims.json --output 答辩PPT.pptx
    python create_ppt.py --qa-only
"""
import os
from pathlib import Path
from typing import List, Dict, Optional

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.ns import qn
    HAS_PPTX = True
except ImportError:
    HAS_PPTX = False
    # 降级提示延迟到 main()：import 阶段不打印，避免污染被导入方的输出


# ============================================================
# 配色方案（学术答辩风格）
# 仅在 python-pptx 可用时构建 RGBColor 常量；缺失时保持 None，
# 模块仍可安全导入并走文本大纲降级路径（_create_text_outline
# 不消费这些常量）。
# ============================================================
if HAS_PPTX:
    TITLE_COLOR = RGBColor(0x1A, 0x3C, 0x6E)       # 深蓝
    ACCENT_COLOR = RGBColor(0xC0, 0x39, 0x2B)       # 暗红（强调）
    BODY_COLOR = RGBColor(0x2C, 0x3E, 0x50)         # 深灰
    BG_COLOR = RGBColor(0xFC, 0xFC, 0xFC)           # 近白
    TABLE_HEADER_BG = RGBColor(0x1A, 0x3C, 0x6E)    # 表头深蓝
    TABLE_HEADER_FG = RGBColor(0xFF, 0xFF, 0xFF)     # 表头白字
    TABLE_ROW_ALT = RGBColor(0xEE, 0xF2, 0xF7)       # 交替行浅蓝
    LIGHT_BLUE = RGBColor(0x34, 0x95, 0xDB)
else:
    TITLE_COLOR = ACCENT_COLOR = BODY_COLOR = BG_COLOR = None
    TABLE_HEADER_BG = TABLE_HEADER_FG = TABLE_ROW_ALT = LIGHT_BLUE = None


def create_presentation(title: str, slides_content: List[Dict],
                        output_path: str = '答辩PPT.pptx') -> str:
    """创建 PPT 演示文稿

    Args:
        title: 演示文稿标题
        slides_content: 每页内容列表 [{title, content, type}]
        output_path: 输出 .pptx 路径

    Returns:
        str: 输出文件路径
    """
    if not HAS_PPTX:
        return _create_text_outline(
            title, slides_content,
            output_dir=os.path.dirname(os.path.abspath(output_path)) or None)

    prs = Presentation()
    prs.slide_width = Inches(13.333)   # 16:9 宽屏
    prs.slide_height = Inches(7.5)

    for i, slide_data in enumerate(slides_content):
        slide_type = slide_data.get('type', 'content')
        if slide_type == 'title':
            _add_title_slide(prs, slide_data)
        elif slide_type == 'section':
            _add_section_slide(prs, slide_data)
        elif slide_type == 'comparison':
            _add_comparison_slide(prs, slide_data)
        else:
            _add_content_slide(prs, slide_data)

    prs.save(output_path)
    return output_path


def _add_title_slide(prs, data: Dict):
    """第 1 页：标题页"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白布局
    # 背景
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG_COLOR
    bg.line.fill.background()

    # 标题
    left, top, width, height = Inches(1.5), Inches(2.5), Inches(10), Inches(2)
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = data.get('title', '数学建模竞赛答辩')
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = TITLE_COLOR
    p.alignment = PP_ALIGN.CENTER

    # 副标题
    subtitle = data.get('subtitle', '')
    if subtitle:
        left, top, _, _ = Inches(1.5), Inches(4.5), Inches(10), Inches(1)
        txBox2 = slide.shapes.add_textbox(left, top, width, Inches(1))
        tf2 = txBox2.text_frame
        p2 = tf2.paragraphs[0]
        p2.text = subtitle
        p2.font.size = Pt(24)
        p2.font.color.rgb = BODY_COLOR
        p2.alignment = PP_ALIGN.CENTER


def _add_section_slide(prs, data: Dict):
    """章节分隔页"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = TITLE_COLOR
    bg.line.fill.background()

    txBox = slide.shapes.add_textbox(
        Inches(2), Inches(3), Inches(9), Inches(1.5))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = data.get('title', '')
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    p.alignment = PP_ALIGN.CENTER


def _set_font(font, size=None, color=None, bold=None):
    """统一字体设置：显式中文字体名（East Asian typeface）+ 常规属性。

    python-pptx 的 font.name 只作用于拉丁字体；中文文本必须同时写入
    rPr 的 a:ea typeface，否则在未安装主题字体的机器上回退为默认宋体。
    """
    if size is not None:
        font.size = size
    if color is not None:
        font.color.rgb = color
    if bold is not None:
        font.bold = bold
    try:
        font.name = "Microsoft YaHei"
        rPr = font._element
        ea = rPr.find(qn('a:ea'))
        if ea is None:
            ea = rPr.makeelement(qn('a:ea'), {})
            rPr.append(ea)
        ea.set('typeface', 'Microsoft YaHei')
    except Exception:
        pass


def _add_content_slide(prs, data: Dict):
    """内容页"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    # 顶部色条
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.15))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT_COLOR
    bar.line.fill.background()

    # 标题
    txBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11), Inches(0.8))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = data.get('title', '')
    for run in p.runs:
        _set_font(run.font, size=Pt(28), color=TITLE_COLOR, bold=True)

    # 内容要点
    content = data.get('content', [])
    if isinstance(content, str):
        content = content.split('\n')
    content = [c for c in content if c.strip()]

    images = data.get('images', [])
    # 版式防重叠：有插图时内容区在 4.4" 处收口，给 4.6" 起的图片带让位；
    # 无插图时保持整页高度。
    content_height = Inches(2.9) if images else Inches(5.5)

    txBox2 = slide.shapes.add_textbox(
        Inches(1.0), Inches(1.5), Inches(11), content_height)
    tf2 = txBox2.text_frame
    tf2.word_wrap = True

    for i, item in enumerate(content):
        if i == 0:
            p = tf2.paragraphs[0]
        else:
            p = tf2.add_paragraph()
        # 识别编号格式
        if item.lstrip().startswith(('•', '▪', '▸', '→', '1.', '2.', '3.')):
            p.text = item
        else:
            p.text = f"• {item}"
        for run in p.runs:
            _set_font(run.font, size=Pt(20), color=BODY_COLOR)
        p.space_after = Pt(12)

    # 页脚
    txBox3 = slide.shapes.add_textbox(
        Inches(0.5), Inches(7.0), Inches(12), Inches(0.4))
    tf3 = txBox3.text_frame
    p3 = tf3.paragraphs[0]
    p3.text = data.get('footer', '')
    p3.font.size = Pt(10)
    p3.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    p3.alignment = PP_ALIGN.RIGHT

    # ⛔ 插图（阶段11门禁：PPT 图表必须复用论文 figures 目录图表，禁止重新绘制）
    # 传入格式：[{'path': '论文/figures/figX.png', 'caption': '论文图N：...', 'note': '详见论文§X.X'}]
    # ⚠️ 必须用 PNG 版（300dpi）——python-pptx 的 add_picture 不支持 PDF；
    #    论文用 PDF 矢量版、PPT 用 PNG 位图版，同一数据两版本。
    if images:
        n_imgs = min(len(images), 3)  # 每页最多 3 张
        zone_left, zone_top, zone_w, zone_h = Inches(0.8), Inches(4.6), Inches(11.7), Inches(2.3)
        img_w = zone_w / n_imgs
        for i, img in enumerate(images[:n_imgs]):
            path = img.get('path', '')
            if path and os.path.exists(path):
                try:
                    slide.shapes.add_picture(path, zone_left + i * img_w,
                                             zone_top, width=img_w - Inches(0.25))
                except Exception as e:
                    print(f"⚠️ 图片插入失败 {path}: {e}")
            # 图注（与论文图号对应）
            caption = img.get('caption', '') or img.get('note', '')
            if caption:
                cap = slide.shapes.add_textbox(
                    zone_left + i * img_w, zone_top + zone_h - Inches(0.25),
                    img_w - Inches(0.25), Inches(0.5))
                cf = cap.text_frame
                cf.word_wrap = True
                cp = cf.paragraphs[0]
                cp.text = caption
                for run in cp.runs:
                    _set_font(run.font, size=Pt(11), color=BODY_COLOR)


def _add_comparison_slide(prs, data: Dict):
    """对比表页"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.15))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT_COLOR
    bar.line.fill.background()

    txBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11), Inches(0.8))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = data.get('title', '')
    for run in p.runs:
        _set_font(run.font, size=Pt(28), color=TITLE_COLOR, bold=True)

    # 表格
    table_data = data.get('table', [])
    if table_data and table_data[0]:
        rows = len(table_data)
        cols = len(table_data[0])
        if rows > 12:
            print(f"⚠️ 对比表 {rows} 行超出单页可读上限，截断至 12 行（其余写入讲稿备注）")
            table_data = table_data[:12]
            rows = 12
        table_shape = slide.shapes.add_table(
            rows, cols, Inches(1), Inches(1.5), Inches(11), Inches(5.5))
        table = table_shape.table

        for r in range(rows):
            for c in range(cols):
                cell = table.cell(r, c)
                cell.text = str(table_data[r][c])
                body_size = Pt(14) if rows <= 6 else (Pt(12) if rows <= 9 else Pt(10))
                for paragraph in cell.text_frame.paragraphs:
                    for run in paragraph.runs:
                        _set_font(run.font,
                                  size=body_size,
                                  color=(TABLE_HEADER_FG if r == 0 else BODY_COLOR),
                                  bold=(r == 0))
                if r == 0:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = TABLE_HEADER_BG
                elif r % 2 == 0:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = TABLE_ROW_ALT


def _create_text_outline(title: str, slides_content: List[Dict],
                         output_dir: Optional[str] = None) -> str:
    """当 python-pptx 不可用时，创建文本版 PPT 大纲"""
    out_dir = output_dir or os.path.join(os.getcwd(), '答辩')
    output_path = os.path.join(out_dir, '答辩大纲.txt')
    os.makedirs(out_dir, exist_ok=True)

    lines = [f"答辩 PPT 大纲: {title}", "=" * 50]
    for i, slide in enumerate(slides_content, 1):
        lines.append(f"\n--- 第 {i} 页: {slide.get('title', '')} ---")
        content = slide.get('content', [])
        if isinstance(content, str):
            content = content.split('\n')
        for item in content:
            if item.strip():
                lines.append(f"  • {item.strip()}")
    lines.append("\n" + "=" * 50)
    lines.append("提示: pip install python-pptx 后可自动生成 .pptx 文件")

    text = '\n'.join(lines)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"文本版 PPT 大纲已保存至: {output_path}")
    return output_path


# ============================================================
# 标准 PPT 结构生成器
# ============================================================

def build_standard_ppt_structure(problem_title: str, questions: List[str],
                                 innovations: List[str],
                                 key_results: Optional[Dict] = None,
                                 figures: Optional[Dict] = None) -> List[Dict]:
    """构建标准答辩 PPT 结构（6-8 页）

    Args:
        problem_title: 赛题标题
        questions: 各问简述
        innovations: 创新点列表
        key_results: 关键结果 {question_name: [{metric, value, comparison}]}
        figures: 论文图表路径映射（阶段11门禁：PPT 图表必须复用论文
                 figures 目录，禁止重新绘制）。键取值：
                 'route'/'q1'/'q2'/'q3'/'q4'/'validation'/'innovation'，
                 值为 [{path, caption, note}] 列表，path 形如
                 '论文/figures/figX.png'（⚠️ 必须 PNG——python-pptx
                 不支持 PDF；论文用 PDF 矢量版，PPT 用 PNG 位图版）。

    Returns:
        List[Dict]: slides_content（可直接传入 create_presentation）
    """
    figures = figures or {}
    slides = []

    # 第 1 页：标题页
    slides.append({
        'type': 'title',
        'title': '数学建模竞赛答辩',
        'subtitle': f'题目: {problem_title}',
    })

    # 第 2 页：问题背景与技术路线图（含论文技术路线图）
    slides.append({
        'type': 'content',
        'title': '问题背景与技术路线',
        'content': [
            f'研究问题: {problem_title}',
            '技术路线: 数据预处理 → EDA洞察 → 建模求解 → 验证 → 结论',
            f'共 {len(questions)} 个问题，采用统一数学框架',
            '核心创新点将在后页详细介绍',
        ],
        'images': figures.get('route', []),
    })

    # 第 3-N 页：各问核心方法 + 关键结果（含论文核心结果图）
    for i, q in enumerate(questions[:4]):  # 最多 4 问
        result_items = [f'核心方法: 见论文第 {i+5} 章']
        if key_results and q in key_results:
            for r in key_results[q]:
                result_items.append(f"{r.get('metric','指标')}: {r.get('value','')} "
                                   f"(对比: {r.get('comparison','')})")
        result_items.append(f'创新点应用: {innovations[min(i, len(innovations)-1)] if innovations else "见后页"}')
        slides.append({
            'type': 'content',
            'title': f'问题 {i+1}: {q}',
            'content': result_items,
            'images': figures.get(f'q{i+1}', []),
        })

    # 创新点总览页
    slides.append({
        'type': 'section',
        'title': '核心创新',
    })
    inno_items = [f'创新 {i+1}: {inv}' for i, inv in enumerate(innovations)]
    inno_items.append('以上创新点均有消融实验验证（见论文附录）')
    slides.append({
        'type': 'content',
        'title': '创新点总览与消融验证',
        'content': inno_items,
        'images': figures.get('innovation', []),
    })

    # 验证与灵敏度（含论文灵敏度图）
    slides.append({
        'type': 'content',
        'title': '验证与灵敏度分析',
        'content': [
            '多方法交叉验证（≥3 种独立方法）',
            'Sobol 全局灵敏度分析（一阶 + 总阶指数）',
            '蒙特卡洛稳健性（参数不确定性量化）',
            '极端情况测试（边界值/退化/噪声）',
            '所有结果均通过统计显著性检验（p<0.05）',
        ],
        'images': figures.get('validation', []),
    })

    # 结论与推广
    slides.append({
        'type': 'content',
        'title': '结论与推广',
        'content': [
            '模型总结与核心贡献',
            '方法的泛化能力与适用范围',
            '局限性与未来改进方向',
            '实际应用价值与社会意义',
        ]
    })

    return slides


# ============================================================
# 10 个预答问题备忘
# 唯一规范来源是 qa_cards.py 的 STANDARD_QUESTIONS（主题/问题/思路）；
# 单独复制本文件到项目时才退回内置同源副本——修改问题清单请改 qa_cards。
# ============================================================

try:
    from qa_cards import STANDARD_QUESTIONS as _CANONICAL_QA_QUESTIONS
except ImportError:  # 独立部署降级：与 qa_cards.py 保持逐字同步的副本
    _CANONICAL_QA_QUESTIONS = None

_FALLBACK_QUESTIONS = [
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

PREPARED_QUESTIONS = [
    (question, hint)
    for (_title, question, hint) in
    (_CANONICAL_QA_QUESTIONS or _FALLBACK_QUESTIONS)
]


def generate_qa_cheatsheet() -> str:
    """生成 10 个预答问题的备忘文档"""
    lines = ["# 答辩预答问题备忘", "", "> 以下 10 个问题覆盖评委提问的 90% 场景。",
             "> 建议每个问题准备 1-2 分钟的流畅回答。", ""]
    for i, (q, hint) in enumerate(PREPARED_QUESTIONS, 1):
        lines.append(f"## {i}. {q}")
        lines.append(f"")
        lines.append(f"**答题思路**: {hint}")
        lines.append(f"")
        lines.append(f"**我的回答**: [填写具体回答]")
        lines.append(f"")
    return '\n'.join(lines)


def load_claims(claims_path: str) -> List[Dict]:
    """读取 `mmflow export-claims` 导出的 JSON（mmflow-defense-cards-input/v1）。

    返回 claims 列表；schema 不符或文件缺失时抛 ValueError，由调用方
    降级为示例骨架，绝不伪造数字。
    """
    import json
    with open(claims_path, 'r', encoding='utf-8') as f:
        document = json.load(f)
    if not isinstance(document, dict) or \
            document.get('schema') != 'mmflow-defense-cards-input/v1' or \
            not isinstance(document.get('claims'), list):
        raise ValueError('claims 文件必须是 mmflow-defense-cards-input/v1 导出格式')
    if not document['claims']:
        # 空 claims 意味着 P7 尚未登记任何 VALID 主张；静默走示例骨架会把
        # 占位内容带进正式答辩材料，必须显式失败让调用方先补登记。
        raise ValueError('claims 为空：请先完成 P7 claim 登记并重新 export-claims')
    return document['claims']


def claims_to_slides(title: str, claims: List[Dict]) -> List[Dict]:
    """把 Registry 导出的 claim 转成"逐问结果"页与"核心结论"页。

    只引用 claim 原文与 result_id，不生成任何新数字。
    """
    slides: List[Dict] = []
    by_question: Dict[str, List[Dict]] = {}
    for claim in claims:
        qid = str(claim.get('question_id') or '综合结论')
        by_question.setdefault(qid, []).append(claim)

    conclusion_rows = [['问题', '核心结论（绑定 Claim）', '支撑 Result']]
    for qid in sorted(by_question):
        items = by_question[qid]
        content_lines = []
        for claim in items:
            statement = str(claim.get('statement', '')).strip()
            result_ids = ', '.join(claim.get('supporting_result_ids', [])) or '—'
            content_lines.append(f"{statement}（{result_ids}）")
            conclusion_rows.append(
                [qid, statement[:40], result_ids[:30] or '—'])
        slides.append({
            'type': 'content',
            'title': f'{qid} 结论',
            'content': content_lines[:4],
        })
    if len(conclusion_rows) > 1:
        slides.append({
            'type': 'comparison',
            'title': '核心结论汇总',
            'table': conclusion_rows,
        })
    return slides


# ============================================================
# 主入口
# ============================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='答辩 PPT 自动生成')
    if not HAS_PPTX:
        print("⚠️ python-pptx 未安装，将输出文本版 PPT 大纲")
        print("   安装: pip install python-pptx")
    parser.add_argument('--title', default='数学建模竞赛答辩',
                        help='PPT 标题')
    parser.add_argument('--output', default='答辩PPT.pptx',
                        help='输出文件路径')
    parser.add_argument('--qa-only', action='store_true',
                        help='仅生成预答问题备忘')
    parser.add_argument('--claims', default=None,
                        help='mmflow export-claims 导出的 JSON 路径；'
                             '提供时自动填充逐问结论页（推荐）')
    args = parser.parse_args()

    out_dir = os.path.dirname(os.path.abspath(args.output))

    if args.qa_only:
        cheatsheet = generate_qa_cheatsheet()
        os.makedirs(out_dir, exist_ok=True)
        memo_path = os.path.join(out_dir, '预答问题备忘.md')
        with open(memo_path, 'w', encoding='utf-8') as f:
            f.write(cheatsheet)
        print(f"预答问题备忘已保存至: {memo_path}")
    else:
        slides: List[Dict] = []
        if args.claims:
            try:
                claims = load_claims(args.claims)
            except (OSError, ValueError) as error:
                raise SystemExit(f"[claims] {error}")
            if claims:
                slides.extend(claims_to_slides(args.title, claims))
            print(f"已从 Registry 导出填充 {len(claims)} 条 claim")
        if not slides:
            # 无 claims 时输出结构骨架（占位文本，须人工替换）
            example_questions = [
                '数据驱动的XX建模与求解',
                '考虑耦合效应的XX优化',
                '多目标权衡与决策建议',
            ]
            example_innovations = [
                '基于XX的XX方法——解决XX无法处理XX的局限',
                '将XX领域的XX定理迁移至本题——非平凡应用',
            ]
            slides = build_standard_ppt_structure(
                problem_title='[在此填写赛题标题]',
                questions=example_questions,
                innovations=example_innovations,
            )
        # --output 参数实际生效
        output = create_presentation(args.title, slides,
                                     output_path=args.output)
        print(f"PPT 已保存至: {output}")
        if HAS_PPTX:
            print(f"共 {len(slides)} 页, 16:9 宽屏格式")

        # 同时生成预答问题备忘（与 PPT 同目录）
        cheatsheet = generate_qa_cheatsheet()
        os.makedirs(out_dir, exist_ok=True)
        memo_path = os.path.join(out_dir, '预答问题备忘.md')
        with open(memo_path, 'w', encoding='utf-8') as f:
            f.write(cheatsheet)
        print(f"预答问题备忘已保存至: {memo_path}")
