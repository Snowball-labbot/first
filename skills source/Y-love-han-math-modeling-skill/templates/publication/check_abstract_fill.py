# -*- coding: utf-8 -*-
"""
check_abstract_fill.py — 摘要页撑满自动验证脚本（AI 自主执行）
用途：阶段 9/10——验证摘要页（第1页）三项判定：
      ① 官方红线（2026 国赛修订稿第三条）：摘要内容（含标题和关键词）
         原则上不超过一页 → 必须用精确方法判定"摘要是否溢出到第 2 页"
      ② 撑满达标线：末行距页面底部 ≤ 5cm（≈ 3-4 行空白，视觉上"基本
         占满"——国奖获奖论文形态）；12pt/1.25 行距/2.5cm 边距下
         1300-1450 字可稳定达到（几何核算：页容量 ≈1765 字，标题区
         ≈4.5 行，1300 字 → 留白 ≈5cm，1450 字 → 留白 ≈3.5cm）
      ③ 冲刺线：末行距页面底部 ≤ 3cm（≈ 2 行空白，"全占满"观感；
         1400-1450 字可达，属加分项非硬门禁）
      ⛔ 注意：12pt/1.25 行距下"≤3cm 且不超页"的窗口仅 ±20 字左右，
         因此 3cm 只作冲刺目标、5cm 为达标线——防止 AI 反复试编译。

⛔ 溢出判定方法（废除"第2页有内容即溢出"的错误逻辑）：
    若以"第 2 页文本区有任何文字 = 摘要溢出"判定，任何正常论文
    第 2 页都有正文（问题重述），必然 100% 误报违规。
    本脚本采用两级判定：
    ① 精确判定（优先）：main.tex 摘要末关键词行后已放置
       \\label{abstractend}（模板已内置），编译后 Grep `main.aux` 中
       \\newlabel{abstractend} 的页码 → ==1 = 摘要完整结束于第 1 页
       （无溢出）；>1 = 摘要溢出 → 违规。
    ② 启发式降级（.aux 缺失或 label 缺失时）：检测第 1 页最后一行
       是否含"关键词"行——含 = 摘要标准结尾在第 1 页 → 无溢出；
       不含 = 无法精确判定 → 输出"无法判定"提示（不判违规，避免误报），
       并提示 AI 检查 main.tex 是否包含 \\label{abstractend}。
    判定优先级：① > ② > 不判定。任何情况下都不再使用
    "第 2 页有正文 = 溢出"的旧逻辑。

依赖：pdfplumber（pip install pdfplumber）
      若不可用，回退到 PyMuPDF（fitz）；两者都不可用则输出无法验证警告

运行方式：python check_abstract_fill.py --pdf 论文/main.pdf
          （脚本自动探测同目录 main.aux；也可 --aux 显式指定）
输出：abstract_fill_check.txt（底部留白 + 溢出检查 + 通过/不通过判定）
"""
from __future__ import annotations

import re
import sys
import argparse
from pathlib import Path

# A4 页面高度（pt）：297mm = 842pt
A4_HEIGHT_PT = 842.0
# 页脚区起点（pt）：2.5cm 下边距 = 71pt → 文本区底部 = 842-71 = 771pt
# ⚠️ 页脚页码位于 771-842pt 区间——测量最后一行时必须排除页脚区，
#    否则页码（总在 ~803pt）会污染"留白"计算，撑满判定永久失效
TEXT_AREA_BOTTOM_PT = A4_HEIGHT_PT - 2.5 * 72.0 / 2.54  # ≈ 771
# 达标线：留白 ≤ 5cm = 141.7pt（≈占页 83%+，"基本占满"）
PASS_BOTTOM_GAP_PT = 5.0 * 72.0 / 2.54  # ≈ 141.73
# 冲刺线：留白 ≤ 3cm = 85.04pt（"全占满"，加分项）
EXCELLENT_BOTTOM_GAP_PT = 3.0 * 72.0 / 2.54  # ≈ 85.04

# 摘要结束 label（main.tex 摘要末关键词行后放置）
ABSTRACT_END_LABEL = 'abstractend'


# ============================================================
# 溢出判定（v2 核心）
# ============================================================

def get_abstract_end_page(pdf_path: Path) -> int | None:
    """从同目录 .aux 读取 \newlabel{abstractend} 的页码（精确判定）

    aux 中记录格式：\newlabel{abstractend}{{1}{1}{标题}{1}{}}
    其中第二个 {} 内为页码。hyperref 可能追加额外 label，用宽松匹配。

    Returns:
        int: 摘要结束标记所在页码；None = 无法从 .aux 判定
    """
    aux_path = pdf_path.with_suffix('.aux')
    if not aux_path.exists():
        return None
    try:
        content = aux_path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return None
    # 匹配 \newlabel{abstractend}{{<编号>}{<页码>}...}
    m = re.search(r'\\newlabel\{' + re.escape(ABSTRACT_END_LABEL) +
                  r'\}\{\{[^{}]*\}\{(\d+)\}', content)
    if m:
        return int(m.group(1))
    return None


def get_last_body_line(pdf_path: Path) -> str | None:
    """提取第 1 页文本区（bottom ≤ 771pt）最后一行文本（启发式降级用）"""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            words = page.extract_words()
            body = [w for w in words if w['bottom'] <= TEXT_AREA_BOTTOM_PT]
            if not body:
                return None
            max_bottom = max(w['bottom'] for w in body)
            last_line = ' '.join(w['text'] for w in body
                                 if abs(w['bottom'] - max_bottom) < 2.0)
            return last_line
    except ImportError:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            page = doc[0]
            lines = []
            for block in page.get_text('dict')['blocks']:
                if block['type'] != 0:
                    continue
                for line in block['lines']:
                    if line['bbox'][3] <= TEXT_AREA_BOTTOM_PT:
                        lines.append((line['bbox'][3], line))
            if not lines:
                return None
            max_bottom = max(b for b, _ in lines)
            text = ' '.join(
                span['text'] for _, line in lines
                if abs(line['bbox'][3] - max_bottom) < 2.0
                for span in line['spans'])
            return text
        except ImportError:
            return None


def judge_overflow(pdf_path: Path) -> tuple[str, str]:
    """溢出判定（v2）：label 精确判定 → 关键词行启发式 → 无法判定

    Returns:
        (verdict, detail)
        verdict: 'ok'（无溢出）/ 'overflow'（违规）/ 'unknown'（无法判定）
    """
    # ① 精确判定：.aux 中 abstractend label 页码
    page = get_abstract_end_page(pdf_path)
    if page is not None:
        if page > 1:
            return ('overflow',
                    f'label {ABSTRACT_END_LABEL} 落在第 {page} 页'
                    '（应为第 1 页）——摘要溢出')
        return ('ok', f'label {ABSTRACT_END_LABEL} 在第 1 页'
                      '，摘要完整结束于第 1 页')

    # ② 启发式降级：第 1 页最后一行是否为关键词行（摘要标准结尾）
    last_line = get_last_body_line(pdf_path)
    if last_line:
        if '关键词' in last_line or 'Keyword' in last_line:
            return ('ok', '第 1 页最后一行含关键词行，摘要完整结束于第 1 页'
                          '（启发式判定）')
        return ('unknown',
                f'第 1 页最后一行不含关键词行（"{last_line[:30]}..."）；'
                '无法从 PDF 精确判定是否溢出——请检查 main.tex 摘要末是否'
                f'包含 label {ABSTRACT_END_LABEL} 并重新编译后再验证')

    # ③ 完全无法判定
    return ('unknown', '第 1 页文本区无内容，无法判定溢出')


# ============================================================
# 第 1 页留白测量
# ============================================================

def check_with_pdfplumber(pdf_path: Path) -> dict:
    """用 pdfplumber 测量第1页最后一行文本底部位置"""
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        if not words:
            return {'ok': False, 'reason': '第1页无文本'}
        # ⚠️ 排除页脚区单词（页码/页脚装饰）——只统计文本区内（bottom ≤ 771pt）
        body_words = [w for w in words if w['bottom'] <= TEXT_AREA_BOTTOM_PT]
        if not body_words:
            return {'ok': False, 'reason': '第1页文本区内无内容'}
        max_bottom = max(w['bottom'] for w in body_words)
        return {'ok': True, 'last_line_bottom': max_bottom}


def check_with_fitz(pdf_path: Path) -> dict:
    """用 PyMuPDF 测量第1页最后一行文本底部位置"""
    import fitz  # PyMuPDF
    doc = fitz.open(pdf_path)
    page = doc[0]
    blocks = page.get_text('dict')['blocks']
    max_bottom = 0
    found = False
    for block in blocks:
        if block['type'] != 0:
            continue
        for line in block['lines']:
            bottom = line['bbox'][3]
            if bottom <= TEXT_AREA_BOTTOM_PT:  # 排除页脚区
                max_bottom = max(max_bottom, bottom)
                found = True
    if not found:
        return {'ok': False, 'reason': '第1页文本区内无内容'}
    return {'ok': True, 'last_line_bottom': max_bottom}


def main():
    # Windows GBK 控制台/管道加固：报告含 emoji，重定向时防 UnicodeEncodeError
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser(description='摘要撑满一页自动验证')
    parser.add_argument('--pdf', required=True, help='PDF 论文文件路径')
    parser.add_argument('--aux', default=None,
                        help='main.aux 路径（默认自动探测 PDF 同目录）')
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"❌ 文件不存在: {pdf_path}")
        sys.exit(1)

    print("=" * 60)
    print("摘要撑满一页验证")
    print("=" * 60)

    result = None
    try:
        result = check_with_pdfplumber(pdf_path)
    except ImportError:
        try:
            result = check_with_fitz(pdf_path)
        except ImportError:
            print("❌ 无法验证：需要 pdfplumber 或 PyMuPDF")
            print("   安装: pip install pdfplumber")
            sys.exit(1)
    except Exception as e:
        print(f"❌ pdfplumber 解析失败: {e}")
        try:
            result = check_with_fitz(pdf_path)
        except Exception as e2:
            print(f"❌ PyMuPDF 解析失败: {e2}")
            sys.exit(1)

    if not result['ok']:
        print(f"❌ {result['reason']}")
        sys.exit(1)

    # ---- 溢出判定（v2）----
    overflow_verdict, overflow_detail = judge_overflow(pdf_path)

    # ---- 留白测量 ----
    gap = result['last_line_bottom']
    gap_cm = (A4_HEIGHT_PT - gap) * 2.54 / 72.0
    fill_ratio = result['last_line_bottom'] / A4_HEIGHT_PT
    pass_gap_cm = PASS_BOTTOM_GAP_PT * 2.54 / 72.0
    exc_gap_cm = EXCELLENT_BOTTOM_GAP_PT * 2.54 / 72.0

    print(f"  摘要页最后一行底部位置: {result['last_line_bottom']:.1f}pt "
          f"({fill_ratio:.1%} 页高)")
    print(f"  距页面底部留白: {gap_cm:.2f} cm (达标线 ≤{pass_gap_cm:.2f} cm，"
          f"冲刺线 ≤{exc_gap_cm:.2f} cm)")
    if overflow_verdict == 'overflow':
        print(f"  摘要溢出: ⚠️ {overflow_detail}")
    elif overflow_verdict == 'ok':
        print(f"  摘要溢出: 无（{overflow_detail}）")
    else:
        print(f"  摘要溢出: ⚠️ 无法判定（{overflow_detail}）")
        print("  （.aux 缺失或未放置 label abstractend——请按模板要求"
              "放置该 label 并重新编译，以获取精确判定）")

    passed = True
    excellent = False
    issues = []
    if overflow_verdict == 'overflow':
        passed = False
        issues.append(f"摘要溢出到第 2 页——{overflow_detail}"
                      "。违反 2026 官方规范第三条（摘要原则上不能超过一页）"
                      "→ 必须精简摘要（目标 1300-1450 字）后重新编译")
    elif overflow_verdict == 'unknown':
        # 无法判定 ≠ 违规：不判死，输出提示（避免 v1 式误报）
        issues.append(f"⚠️ 溢出无法精确判定：{overflow_detail}")

    if gap_cm > pass_gap_cm:
        passed = False
        issues.append(f"摘要底部留白 {gap_cm:.2f}cm > 达标线 {pass_gap_cm:.2f}cm——"
                      f"未撑满（国奖获奖论文摘要页基本全占满）→ 扩充摘要至 "
                      f"1300-1450 字（目标 1400 字）后重新编译")
    elif gap_cm <= exc_gap_cm:
        excellent = True

    if passed:
        if excellent:
            print("  ✅ 摘要页达标：全占满（≤3cm 冲刺线）+ 未溢出")
        else:
            print("  ✅ 摘要页达标：基本占满（≤5cm 达标线）+ 未溢出")
    else:
        for issue in issues:
            print(f"  ⚠️ {issue}")

    # 写报告
    report_path = pdf_path.parent / 'abstract_fill_check.txt'
    lines = [
        "=" * 60, "摘要页撑满验证报告", "=" * 60,
        f"PDF 文件: {pdf_path}",
        f"最后一行底部: {result['last_line_bottom']:.1f}pt",
        f"占页率: {fill_ratio:.1%}",
        f"底部留白: {gap_cm:.2f} cm (达标线 ≤{pass_gap_cm:.2f} cm)",
        f"冲刺线(全占满): {exc_gap_cm:.2f} cm {'✅' if excellent else '—'}",
        f"摘要溢出判定: "
        f"{'无溢出' if overflow_verdict == 'ok' else '有溢出(违规)' if overflow_verdict == 'overflow' else '无法判定'}",
        f"  判定依据: {overflow_detail}",
        f"结果: {'✅ 通过' if passed else '❌ 不通过'}",
        "=" * 60,
        "说明: ①达标线=留白≤5cm（视觉[基本占满]，国奖获奖论文形态）",
        "      ②冲刺线=留白≤3cm（[全占满]，1400-1450字可达，加分项）",
        "      ③官方红线=摘要不超过一页（2026修订稿第三条）；溢出判定",
        "        优先用 main.aux 的 \\label{abstractend} 页码（精确），",
        "        降级为关键词行启发式（无法判定时不判违规，避免误报）",
        "      ④未达标 → 扩充摘要至1300-1450字（目标1400字）后重新编译",
        "      ⛔ 美赛：不运行本脚本（Summary Sheet 按 8.9 英文摘要标准，",
        "         占页 1/2-2/3 即可，与国赛'撑满'方向相反）",
        "=" * 60,
    ]
    report_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"\n报告已保存至: {report_path}")

    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
