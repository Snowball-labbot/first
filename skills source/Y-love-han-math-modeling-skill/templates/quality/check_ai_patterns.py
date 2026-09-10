# -*- coding: utf-8 -*-
"""
check_ai_patterns.py — AI率自查代理脚本（AI 自主执行，无需外部工具）
用途：阶段 10 提交前——扫描论文中的 AI 高频写作模式，作为 AI 率的外部检测代理指标
      （最终 AI 率检测以 GPTZero/维普 等外部工具为准，本脚本执行 AI 侧全部可做的降AI自查）

运行方式：python check_ai_patterns.py --tex 论文/main.tex
输出：ai_pattern_report.txt（含各模式计数 + 总分 + 通过/不通过判定）
"""
import re
import sys
import argparse
from pathlib import Path

# GBK 等 Legacy 控制台安全输出：报告文件始终为 UTF-8，stdout 不因 emoji/中文崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ============================================================
# AI 高频模式清单（中文论文 AI 检测特征）
# ============================================================
AI_PATTERNS = [
    # 机械连接词
    (r'首先[，,].{0,30}其次', '机械连接词"首先…其次…"', 2),
    (r'再次[，,].{0,30}最后', '机械连接词"再次…最后…"', 2),
    (r'综上所述', '模板总结"综上所述"', 1),
    (r'总而言之', '模板总结"总而言之"', 1),
    (r'接下来[，,].{0,20}(将|会|需要)', '模板过渡"接下来将…"', 1),
    # 空洞评价
    (r'具有良好的性能', '空洞评价"具有良好的性能"', 2),
    (r'表现出良好的', '空洞评价"表现出良好的"', 2),
    (r'在一定程度上', '模糊限定"在一定程度上"', 1),
    (r'具有一定的', '模糊限定"具有一定的"', 1),
    (r'效果良好', '空洞评价"效果良好"', 2),
    (r'性能优越', '空洞评价"性能优越"', 2),
    # 模板表述
    # ⚠️ 刻意排除：'本文的主要贡献'（摘要贡献段强制句式）、'基于[^，。]{4,20}的'
    # （标题模板"基于XX的建模与优化研究"强制格式）——竞赛规范强制结构不计入。
    (r'可以看出', '模板"可以看出"', 1),
    (r'从图\s*\d*\s*中可以看出', '模板"从图中可以看出"', 2),
    (r'由上表可知', '模板"由上表可知"', 2),
    (r'本文提出了一种', '模板"本文提出了一种"', 1),
    (r'通过分析我们可以', '模板"通过分析我们可以"', 2),
    (r'基于以上分析', '模板"基于以上分析"', 2),
    # 重复句式
    (r'该模型[^。]{0,30}该模型', '重复"该模型"连续使用', 2),
    # 参考指标（权重 0：只显示命中数，不计入总分——标题模板的"基于XX的"不算）
    (r'基于[^，。]{4,20}的', '参考:"基于…的"结构(标题模板允许1处)', 0),
]

# ============================================================
# AI 高频模式清单（英文论文 MCM/ICM 用）
# ============================================================
AI_PATTERNS_EN = [
    # 机械连接词与过渡
    (r'\b(?:Furthermore|Moreover|Additionally|Notably),', '机械过渡词开头(Furthermore/Moreover…)', 1),
    (r'\bIn conclusion\b', '模板总结"In conclusion"', 1),
    (r'\bIn summary\b', '模板总结"In summary"', 1),
    # 填充语与空洞表述
    (r'\b[Ii]t is (?:worth noting|important to note|worth mentioning) that\b', '填充语"It is worth noting that…"', 2),
    (r'\bplays? a (?:crucial|vital|pivotal|key|significant) role in\b', '空洞表述"plays a crucial role in"', 2),
    (r'\ba comprehensive (?:framework|approach|analysis|study)\b', '空洞表述"a comprehensive framework/approach…"', 1),
    # AI 高频词与模板短语
    (r'\bdelv(?:e|es|ed|ing) into\b', 'AI 高频词"delve into"', 2),
    (r'\bpaves? the way for\b', '模板短语"paves the way for"', 2),
    (r'\bin the realm of\b', '模板短语"in the realm of"', 2),
    (r'\bharness(?:es|ing)? the power of\b', '模板短语"harnessing the power of"', 2),
    (r'\bnavigat(?:e|ing) the complexit(?:y|ies)(?: of)?\b', '模板短语"navigating the complexities"', 2),
    (r'\bund(?:erscore|erlines)s? the (?:importance|significance) of\b', '模板短语"underscores the importance of"', 1),
    (r'\bfoster(?:s|ing)? [^.,;]{0,30}(?:innovation|collaboration|growth)\b', '模板短语"fostering innovation…"', 2),
    (r'\bseamless(?:ly)? integrat\w+\b', '模板短语"seamlessly integrates"', 2),
    (r'\bin today\'s\b', '模板短语"in today\'s …"', 2),
    (r'\bleverag(?:e|es|ing)\b', 'AI 高频词"leverage/leveraging"', 1),
    # 句式参考（权重 0：偶发合法，只提示不计分）
    (r'\bnot only\b[^.;]{0,80}?\bbut also\b', '参考:"not only…but also"句式(高频重复才需改写)', 0),
]


def load_tex(path: Path) -> str:
    """读取 LaTeX 文件，剔除注释和代码块"""
    content = path.read_text(encoding='utf-8')
    # 剔除注释行
    lines = [l for l in content.split('\n') if not l.strip().startswith('%')]
    content = '\n'.join(lines)
    # 剔除附录代码块（listings 环境内不是论文正文）
    content = re.sub(r'\\begin\{lstlisting\}.*?\\end\{lstlisting\}',
                     '', content, flags=re.DOTALL)
    return content


def extract_chinese_sentences(content: str) -> list:
    """提取中文学术句（用于句长标准差计算）"""
    # 去掉 LaTeX 命令和公式
    text = re.sub(r'\\[a-zA-Z]+(\[[^\]]*\])?(\{[^}]*\})?', '', content)
    text = re.sub(r'\$[^$]*\$', '', text)
    sentences = re.split(r'[。！？]', text)
    return [s.strip() for s in sentences
            if len(re.findall(r'[\u4e00-\u9fff]', s)) >= 10]


def calc_sentence_std(sentences: list, unit: str = 'zh') -> float:
    """句长标准差——AI 生成文本句长规律性强，标准差偏低。zh 按中文字符，en 按词数"""
    if len(sentences) < 20:
        return 0.0
    if unit == 'zh':
        lengths = [len(re.findall(r'[\u4e00-\u9fff]', s)) for s in sentences]
    else:
        lengths = [len(s.split()) for s in sentences]
    mean = sum(lengths) / len(lengths)
    var = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    return var ** 0.5


def scan_patterns(content: str) -> list:
    """扫描全部 AI 模式（中英文清单），返回 [(模式名, 计数, 权重)]"""
    results = []
    for pattern, name, weight in [*AI_PATTERNS, *AI_PATTERNS_EN]:
        count = len(re.findall(pattern, content))
        if count > 0:
            results.append((name, count, weight))
    return results


def detect_language(content: str) -> str:
    """按 CJK 字符量判断文档语言：zh=中文论文，en=英文论文（MCM/ICM）"""
    cjk = len(re.findall(r'[\u4e00-\u9fff]', content))
    return 'zh' if cjk >= 200 else 'en'


def extract_english_sentences(content: str) -> list:
    """提取英文学术句（用于句长标准差计算，单位=词数）"""
    text = re.sub(r'\\[a-zA-Z]+(\[[^\]]*\])?(\{[^}]*\})?', '', content)
    text = re.sub(r'\$[^$]*\$', '', text)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if len(s.split()) >= 8]


def main():
    parser = argparse.ArgumentParser(description='AI率自查代理扫描')
    parser.add_argument('--tex', required=True, help='LaTeX 论文文件路径')
    args = parser.parse_args()

    tex_path = Path(args.tex)
    if not tex_path.exists():
        print(f"❌ 文件不存在: {tex_path}")
        sys.exit(1)

    print("=" * 60)
    print("AI 率自查代理扫描")
    print("=" * 60)

    content = load_tex(tex_path)
    hits = scan_patterns(content)
    lang = detect_language(content)
    if lang == 'zh':
        sentences = extract_chinese_sentences(content)
        unit_label = '字'
    else:
        sentences = extract_english_sentences(content)
        unit_label = '词'
    std = calc_sentence_std(sentences, unit=lang)

    # 计分：每处命中 + 权重，总分 = 命中加权分
    total_score = sum(count * weight for _, count, weight in hits)
    n_sentences = len(sentences)

    print(f"\n【1】AI 高频模式扫描（中文 {len(AI_PATTERNS)} 种 + 英文 {len(AI_PATTERNS_EN)} 种；文档语言: {lang}）")
    if hits:
        for name, count, weight in hits:
            print(f"  ⚠️ {name}: {count} 处 (权重{weight})")
    else:
        print("  ✅ 未发现 AI 高频模式")

    print(f"\n【2】句长统计分析")
    print(f"  有效句数: {n_sentences}")
    print(f"  句长标准差: {std:.1f} {unit_label} (参考: AI文本常<5, 人类文本常>8)")
    if n_sentences < 20:
        print("  ⚠️ 有效句数过少，句长标准差不可靠")

    print(f"\n【3】判定")
    ai_risk = '低'
    issues = []
    if total_score >= 5:
        ai_risk = '高'
        issues.append(f"AI模式命中分 {total_score} ≥ 5 → 需逐处改写")
    if 0 < total_score < 5:
        ai_risk = '中'
        issues.append(f"AI模式命中分 {total_score} 在1-4之间 → 建议改写高分项")
    if n_sentences >= 20 and std < 5:
        ai_risk = '中'
        issues.append(f"句长标准差 {std:.1f} < 5 → 句长规律性过强，需打破句长节奏")
    if n_sentences >= 20 and std < 8:
        issues.append(f"句长标准差 {std:.1f} < 8 → 建议增加长短句交替（冲刺档目标>8）")

    print(f"  AI风险等级: {ai_risk}")
    for issue in issues:
        print(f"  ⚠️ {issue}")
    if not issues:
        print("  ✅ 全部指标通过")

    # 写报告
    # ⚠️ 报告写到当前工作目录（工作区根）——阶段 10 门禁按
    #    根目录 Glob 12 项产物；
    #    与门禁 Glob 位置不一致导致 AI 误判产物缺失。
    report_path = Path.cwd() / 'ai_pattern_report.txt'
    lines = [
        "=" * 60, "AI 率自查代理报告", "=" * 60,
        f"扫描文件: {tex_path}",
        f"文档语言: {lang}",
        f"AI模式命中分: {total_score} (阈值: <5 通过)",
        f"句长标准差: {std:.1f} {unit_label} (目标: >8, 最低: >5)",
        f"AI风险等级: {ai_risk}",
        "=" * 60,
        "说明: 本报告为 AI 侧自查代理指标。最终 AI 率检测以外部工具",
        "(GPTZero/维普/知网AIGC检测) 为准。若本报告判定不通过,",
        "须按降AI策略改写后重新扫描,直至通过。",
        "=" * 60,
    ]
    if hits:
        lines.append("命中模式明细:")
        for name, count, weight in hits:
            lines.append(f"  {name}: {count} 处")
    report_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"\n报告已保存至: {report_path}")

    sys.exit(0 if ai_risk == '低' else 1)


if __name__ == '__main__':
    main()
