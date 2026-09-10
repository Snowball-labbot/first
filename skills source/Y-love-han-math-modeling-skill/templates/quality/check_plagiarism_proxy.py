# -*- coding: utf-8 -*-
"""
check_plagiarism_proxy.py — 查重代理自查脚本（AI 自主执行）
用途：阶段 10 提交前——扫描论文与模板/常见表述的 n-gram 重合度
      作为查重的 AI 侧代理指标（最终查重以维普/万方为准）

运行方式：python check_plagiarism_proxy.py --tex 论文/main.tex --template templates/main.tex
输出：plagiarism_proxy_report.txt（重合片段 + 判定）
"""
import re
import sys
import argparse
from pathlib import Path

# 学术写作常见高频片段（查重系统通常标记的模板句）
# ⚠️ 刻意排除 skill 强制要求的表述（"针对问题X"摘要段开头、章节名
#     "问题分析/模型假设/符号说明/模型评价与推广"、"本文的主要贡献在于"
#     贡献段、标题模板"基于XX的…"）——这些是竞赛规范强制结构，
#     不应被判为"模板句"（否则合规论文必失败，门禁不可满足）。
COMMON_PHRASES = [
    '随着社会的发展和科学技术的进步', '随着科学技术的飞速发展', '近年来',
    '本文从以下几个方面', '首先对问题进行分析', '建立数学模型',
    '对模型进行求解', '对结果进行分析', '得出结论',
    '通过以上分析可以得出', '从上述结果可以看出', '模型的建立与求解',
    '本文提出了一种', '基于以上分析', '综上所述', '总而言之',
    '具有良好的性能', '在一定程度上', '具有重要意义',
    '为了提高模型的精度', '考虑实际情况', '在现实中',
    '不难发现', '显而易见', '众所周知',
]


def load_tex(path: Path) -> str:
    content = path.read_text(encoding='utf-8')
    lines = [l for l in content.split('\n') if not l.strip().startswith('%')]
    content = '\n'.join(lines)
    content = re.sub(r'\\begin\{lstlisting\}.*?\\end\{lstlisting\}',
                     '', content, flags=re.DOTALL)
    return content


def calc_ngram_repetition(content: str, n=8) -> float:
    """计算 n-gram 重复率：全文重复 n-gram 数 / 总 n-gram 数

    ⚠️ 剔除 LaTeX 命令（\\begin{figure}、\\centering 等每图重复的
    排版样板——它们不是论文内容，会制造假阳性重复率）。
    """
    text = re.sub(r'\\[a-zA-Z]+(\[[^\]]*\])?(\{[^}]*\})?', '', content)
    text = re.sub(r'[{}]', '', text)
    chars = re.sub(r'\s+', '', text)
    if len(chars) < n * 2:
        return 0.0
    ngrams = [chars[i:i+n] for i in range(len(chars) - n + 1)]
    total = len(ngrams)
    seen = set()
    dup = 0
    for g in ngrams:
        if g in seen:
            dup += 1
        else:
            seen.add(g)
    return dup / total


def scan_common_phrases(content: str) -> list:
    hits = []
    for phrase in COMMON_PHRASES:
        count = len(re.findall(re.escape(phrase), content))
        if count > 0:
            hits.append((phrase, count))
    return hits


def main():
    parser = argparse.ArgumentParser(description='查重代理自查')
    parser.add_argument('--tex', required=True, help='LaTeX 论文文件路径')
    parser.add_argument('--template', required=True, help='模板 LaTeX 文件路径')
    args = parser.parse_args()

    tex_path = Path(args.tex)
    tmpl_path = Path(args.template)
    if not tex_path.exists() or not tmpl_path.exists():
        print("❌ 文件不存在")
        sys.exit(1)

    print("=" * 60)
    print("查重代理自查扫描")
    print("=" * 60)

    content = load_tex(tex_path)
    tmpl_content = load_tex(tmpl_path)

    # 1. 与模板的重合（复制模板未填充部分）
    tmpl_lines = set(l.strip() for l in tmpl_content.split('\n') if l.strip())
    paper_lines = set(l.strip() for l in content.split('\n') if l.strip())
    overlap = paper_lines & tmpl_lines
    # 过滤掉 LaTeX 命令与样式行（\begin{figure}、{\zihao...} 等属于
    # 格式非内容——过滤以 "{" 开头的段落样式行，避免模板格式行
    # 被误计为"模板重合内容"）
    content_overlap = [l for l in overlap
                       if not l.startswith('\\') and not l.startswith('{')
                       and len(l) > 5]
    tmpl_overlap_pct = len(content_overlap) / max(len(paper_lines), 1) * 100

    # 2. 高频模板句
    phrase_hits = scan_common_phrases(content)

    # 3. n-gram 重复率
    rep_rate = calc_ngram_repetition(content)

    print(f"\n【1】与模板重合内容行: {len(content_overlap)} 行 "
          f"({tmpl_overlap_pct:.1f}%)")
    for line in content_overlap[:10]:
        print(f"  ⚠️ {line[:60]}")

    print(f"\n【2】常见模板句命中: {len(phrase_hits)} 种")
    for phrase, count in phrase_hits:
        print(f"  ⚠️ \"{phrase}\": {count} 处")

    print(f"\n【3】n-gram 重复率: {rep_rate:.2%} "
          f"(参考: 正常论文 <5%, 高重复 >10%)")

    print(f"\n【4】判定")
    issues = []
    if tmpl_overlap_pct > 2:
        issues.append(f"与模板重合 {tmpl_overlap_pct:.1f}% > 2% → 存在未填充模板句")
    if len(phrase_hits) >= 8:
        issues.append(f"常见模板句 {len(phrase_hits)} 种 ≥ 8 → 模板化表述过多")
    if rep_rate > 0.10:
        issues.append(f"n-gram 重复率 {rep_rate:.2%} > 10% → 内容重复度高")
    if not issues:
        print("  ✅ 全部指标通过")

    for issue in issues:
        print(f"  ⚠️ {issue}")

    # 写报告
    # ⚠️ 报告写到当前工作目录（工作区根）——阶段 10 门禁按
    #    根目录 Glob 12 项产物；
    #    与门禁 Glob 位置不一致导致 AI 误判产物缺失。
    report_path = Path.cwd() / 'plagiarism_proxy_report.txt'
    lines = [
        "=" * 60, "查重代理自查报告", "=" * 60,
        f"与模板重合: {tmpl_overlap_pct:.1f}% (阈值: ≤2%)",
        f"常见模板句: {len(phrase_hits)} 种 (阈值: <8)",
        f"n-gram重复率: {rep_rate:.2%} (阈值: ≤10%)",
        "=" * 60,
        "说明: 本报告为 AI 侧查重代理指标。最终查重以维普/万方为准。",
        "若判定不通过 → 逐处改写模板句/重复片段 → 重新扫描直至通过。",
        "用户提交前: ①维普/万方查重 ≤10% ②AI率外部检测 ≤15% ③抽查5篇文献DOI",
        "=" * 60,
    ]
    if content_overlap:
        lines.append("模板重合内容行:")
        for line in content_overlap[:10]:
            lines.append(f"  {line[:60]}")
    if phrase_hits:
        lines.append("模板句命中明细:")
        for phrase, count in phrase_hits:
            lines.append(f"  {phrase}: {count} 处")
    report_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"\n报告已保存至: {report_path}")

    sys.exit(0 if not issues else 1)


if __name__ == '__main__':
    main()
