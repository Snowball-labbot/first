# -*- coding: utf-8 -*-
"""
verify_consistency.py — 代码-论文一致性自动验证脚本
用途：扫描论文 LaTeX 源码中的所有数值，与代码输出日志交叉验证
      检查图表引用完整性、代码可运行性、公式标签一致性、参考文献可追溯性
运行方式：python verify_consistency.py --tex main.tex --code_dir 代码/ --log_dir 结果/
输出：consistency_report.txt（5 类验证总报告）
"""
import re
import os
import csv
import json
import ast
import sys
from pathlib import Path
from typing import Dict, List


class ConsistencyVerifier:
    """代码-论文一致性验证器（5 类验证）"""

    def __init__(self, tex_path: str, code_dir: str, log_dir: str):
        self.tex_path = Path(tex_path)
        self.code_dir = Path(code_dir)
        self.log_dir = Path(log_dir)
        self.tex_content = self._read(self.tex_path)
        self.results = {}

    @staticmethod
    def _read(path: Path) -> str:
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                return handle.read()
        except FileNotFoundError:
            return ''

    # ================================================================
    # V1: 数值结果一致性
    # ================================================================
    # 仅校验"结果类数值"（正文叙述中的数值），并排除四类必然匹配不到的
    # 非结果类数值——否则参考文献年份(2024)、图宽系数(0.85\textwidth)、
    # 页码、公式中的常数会让验证永远失败（假阳性）：
    #   ① 参考文献区（thebibliography 内所有行）
    #   ② LaTeX 排版参数行（\includegraphics 尺寸、\caption、\label、
    #      \ref、\cite、\section、\footnote 等）
    #   ③ 纯年份（19xx/20xx）
    #   ④ 页码范围（"123-45" 式连字符数值）
    # ⚠️ 刻意不跳过 \caption 行——图注中的结果数值（"RMSE=0.0234" 等）
    #    是溯源核对的重点对象，必须参与数值匹配。
    SKIP_LINE_PATTERNS = [
        r'\\bibitem', r'\\includegraphics', r'\\label',
        r'\\ref\{', r'\\eqref', r'\\cref', r'\\cite', r'\\section',
        r'\\subsection', r'\\subsubsection', r'\\pageref', r'\\footnote',
        r'\\begin\{thebibliography', r'\\item',
    ]

    def _is_skip_line(self, line: str) -> bool:
        """该行属于排版/参考文献等非结果行 → 跳过数值校验"""
        if any(re.search(p, line) for p in self.SKIP_LINE_PATTERNS):
            return True
        return False

    def verify_numerical(self, rel_tol=0.01, abs_tol=1e-9) -> Dict:
        """验证论文结果数值是否在代码输出中找到匹配

        判定标准（v2 修订）：匹配率 ≥90% 即通过；未匹配项输出为
        "待人工核查清单"（供 AI 逐条确认是否属结果数值或论文叙述数），
        不再要求 0 未匹配（年份/图宽等非结果数不应判为失败）。
        """
        issues, matched, unmatched = [], 0, []

        # 从 LaTeX 提取数值（逐行，先过滤非结果行）
        tex_nums = []
        content = '\n'.join(l for l in self.tex_content.split('\n')
                            if not l.strip().startswith('%'))
        pattern = r'(?<![\d.])(\d+\.\d{2,}(?:[eE][+-]?\d+)?|\d{4,}(?:[eE][+-]?\d+)?)(?![\d.])'
        for lineno, line in enumerate(content.split('\n'), 1):
            if self._is_skip_line(line):
                continue
            # 跳过纯年份（19xx/20xx 独立出现）
            line_noyear = re.sub(r'(?<!\d)(19|20)\d{2}(?![\d.])', '', line)
            # 跳过页码范围（如 12-15、pp. 123-125）
            line_noyear = re.sub(r'\d{1,3}\s*[-–]\s*\d{1,3}', '', line_noyear)
            for m in re.finditer(pattern, line_noyear):
                try:
                    val = float(m.group(1))
                except ValueError:
                    continue
                ctx_start = max(0, m.start() - 40)
                ctx_end = min(len(line_noyear), m.end() + 40)
                tex_nums.append({
                    'value': val, 'raw': m.group(1),
                    'context': line_noyear[ctx_start:ctx_end].replace('\n', ' ').strip(),
                    'line': lineno
                })

        # 从代码输出加载数值（所有 .csv/.txt 中的数字构成"数值池"——
        # 说明：此为代理验证，匹配到任意日志/CSV 数字即视为可溯源；
        # 未匹配项必须逐条人工核查，防止幻觉数值漏网）
        code_nums = []
        for csv_f in self.log_dir.glob('*.csv'):
            try:
                for row in csv.reader(open(csv_f, 'r', encoding='utf-8')):
                    for cell in row:
                        try:
                            code_nums.append({'value': float(cell), 'source': csv_f.name})
                        except ValueError:
                            pass
            except Exception:
                pass
        for txt_f in self.log_dir.glob('*.txt'):
            try:
                for line in open(txt_f, 'r', encoding='utf-8'):
                    for m in re.finditer(r'\d+\.\d{2,}(?:[eE][+-]?\d+)?|\d{4,}(?:[eE][+-]?\d+)?', line):
                        try:
                            code_nums.append({'value': float(m.group()), 'source': txt_f.name})
                        except ValueError:
                            pass
            except Exception:
                pass

        # 交叉匹配
        significant = [n for n in tex_nums if abs(n['value']) >= 0.001 or len(n['raw']) >= 4]
        for tn in significant:
            found = False
            for cn in code_nums:
                diff = abs(tn['value'] - cn['value'])
                threshold = max(rel_tol * max(abs(tn['value']), abs(cn['value'])), abs_tol)
                if diff <= threshold:
                    matched += 1
                    found = True
                    break
            if not found:
                unmatched.append(tn)

        total = len(significant)
        match_rate = matched / total if total > 0 else 0
        # v2：匹配率 ≥90% 即通过（未匹配项多为叙述性数字，如"第2种方法"、
        # 表内统计量描述等），未匹配项作为人工核查清单输出，不直接判死。
        for item in unmatched[:50]:
            issues.append(
                f"[待人工核查] 行{item.get('line','?')}: {item['raw']} 未在代码输出中找到匹配 "
                f"({item.get('context','')[:60]})——请逐条确认：属结果数值→修论文/代码；"
                f"属叙述性数字→记录说明即可")
        if len(unmatched) > 50:
            issues.append(
                f"[待人工核查] 另有 {len(unmatched) - 50} 个未匹配数值（报告仅列前 50 个，"
                f"总数 {len(unmatched)} 个）——请按同法逐条核查")

        self.results['numerical'] = {
            # total >= 3：防止"数值量过少的文档"假阴性（真实论文数百数值，
            # 该下限仅为排除空文档；正文不足 3 个结果数值 = 论文本身不合格）
            'status': match_rate >= 0.90 and total >= 3,
            'issues': issues,
            'stats': {'total': total, 'matched': matched,
                      'unmatched': len(unmatched), 'match_rate': f'{match_rate:.1%}',
                      'review_items': len(unmatched)}
        }
        return self.results['numerical']

    # ================================================================
    # V2: 图表数据一致性
    # ================================================================
    def verify_figure_table(self) -> Dict:
        """验证图表引用完整性"""
        issues = []
        fig_refs = re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', self.tex_content)
        figures_dir = self.tex_path.parent / 'figures'

        for fig_path in fig_refs:
            full = figures_dir / fig_path
            found = full.exists()
            if not found:
                for ext in ['.png', '.pdf', '.jpg', '.jpeg', '.eps']:
                    if (figures_dir / f'{fig_path}{ext}').exists():
                        found = True
                        break
            if not found:
                issues.append(f"图表文件不存在: {fig_path}")

        all_labels = set(re.findall(r'\\label\{([^}]+)\}', self.tex_content))
        all_refs = re.findall(r'\\ref\{([^}]+)\}', self.tex_content)
        for ref in all_refs:
            if ref not in all_labels:
                issues.append(f"引用 \\ref{{{ref}}} 无对应 label")

        self.results['figure_table'] = {
            'status': len(issues) == 0,
            'issues': issues,
            'stats': {'fig_refs': len(fig_refs), 'labels': len(all_labels), 'unresolved_refs': len([r for r in all_refs if r not in all_labels])}
        }
        return self.results['figure_table']

    # ================================================================
    # V3: 代码完整性验证
    # ================================================================
    def verify_code_integrity(self) -> Dict:
        """验证代码文件语法和完整性"""
        issues = []
        py_files = list(self.code_dir.glob('*.py'))
        if not py_files:
            issues.append("代码目录中未找到 .py 文件")

        # ⛔ 标准库白名单：用 sys.stdlib_module_names 动态获取
        #    （Python 3.10+，覆盖 argparse 等全部标准库）；硬编码清单
        #    漏掉 argparse 会导致每个用 argparse 的脚本被误报"未声明依赖"。
        try:
            stdlib = set(sys.stdlib_module_names)
        except AttributeError:  # Python < 3.10 兜底
            stdlib = {'os', 'sys', 're', 'json', 'math', 'datetime', 'pathlib',
                      'typing', 'collections', 'itertools', 'functools',
                      'warnings', 'subprocess', 'csv', 'ast', 'argparse'}
        # 本地模块豁免：项目内脚本互相 import（如 from utils import）
        #    不是第三方依赖——utils 不应报"未在 requirements.txt 声明"，
        #    否则 V3 代码完整性检查在标准工作流下必然失败。
        local_modules = {f.stem for f in py_files}

        for py_f in py_files:
            content = self._read(py_f)
            if not content:
                issues.append(f"代码文件为空: {py_f.name}")
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                issues.append(f"{py_f.name}: 语法错误 行{e.lineno}: {e.msg}")

            if '__main__' not in content and py_f.name not in ('utils.py', 'requirements.txt'):
                issues.append(f"{py_f.name}: 缺少 if __name__ == '__main__' 入口")

            imports = set()
            for m in re.finditer(r'(?:^|\n)\s*(?:import|from)\s+([\w.]+)', content):
                imports.add(m.group(1).split('.')[0])
            req_path = self.code_dir / 'requirements.txt'
            req_content = self._read(req_path).lower() if req_path.exists() else ''
            pkg_map = {'sklearn': 'scikit-learn', 'cv2': 'opencv-python',
                       'PIL': 'Pillow', 'yaml': 'PyYAML',
                       'fitz': 'PyMuPDF'}  # fitz 是 PyMuPDF 的导入名
            for imp in imports - stdlib - local_modules:
                pkg = pkg_map.get(imp, imp).lower()
                if pkg not in req_content:
                    issues.append(f"{py_f.name}: import '{imp}' 未在 requirements.txt 中声明")

        if not (self.code_dir / 'requirements.txt').exists():
            issues.append("缺少 requirements.txt")

        self.results['code_integrity'] = {
            'status': len(issues) == 0,
            'issues': issues,
            'stats': {'code_files': len(py_files), 'files': [f.name for f in py_files]}
        }
        return self.results['code_integrity']

    # ================================================================
    # V4: 公式一致性
    # ================================================================
    def verify_formula(self) -> Dict:
        """验证公式标签和引用一致性"""
        issues = []
        eq_labels = set(re.findall(r'\\label\{(eq:[^}]+)\}', self.tex_content))
        eq_refs = re.findall(r'\\(?:ref|eqref|cref)\{(eq:[^}]+)\}', self.tex_content)
        equations = re.findall(r'\\begin\{equation\}(.*?)\\end\{equation\}', self.tex_content, re.DOTALL)

        unlabeled = sum(1 for eq in equations if '\\label' not in eq)
        if unlabeled:
            issues.append(f"{unlabeled} 个编号公式缺少 \\label")

        for ref in eq_refs:
            if ref not in eq_labels:
                issues.append(f"公式引用 {ref} 无对应 label")

        for label in eq_labels:
            if not re.search(r'\\(?:ref|eqref|cref)\{' + re.escape(label) + r'\}', self.tex_content):
                issues.append(f"公式 label {label} 已定义但未引用")

        self.results['formula'] = {
            'status': len(issues) == 0,
            'issues': issues,
            'stats': {'total_eqs': len(equations), 'unlabeled': unlabeled, 'labels': len(eq_labels), 'refs': len(eq_refs)}
        }
        return self.results['formula']

    # ================================================================
    # V5: 参考文献可追溯性
    # ================================================================
    def verify_reference(self) -> Dict:
        """验证参考文献引用和被引一致性"""
        issues = []
        bibitems = re.findall(r'\\bibitem\{([^}]+)\}', self.tex_content)
        bib_set = set(bibitems)
        cite_keys = set()
        # ⛔ 剔除 \newcommand 宏定义行后再匹配 \cite——
        #    宏定义体（如 \newcommand{\upcite}[1]{\textsuperscript{\cite{#1}}}）
        #    中的 \cite{#1} 会被误匹配为"引用 #1"，导致假阳性"引用未找到"。
        tex_no_macro = '\n'.join(
            l for l in self.tex_content.split('\n')
            if not l.strip().startswith('\\newcommand'))
        for m in re.finditer(r'\\(?:cite|upcite|citep|citet)\{([^}]+)\}',
                             tex_no_macro):
            for key in m.group(1).split(','):
                cite_keys.add(key.strip())

        for key in cite_keys - bib_set:
            issues.append(f"引用 {key} 在参考文献列表中未找到")
        for key in bib_set - cite_keys:
            issues.append(f"参考文献 {key} 在正文中未被引用")
        if len(bibitems) < 15:
            issues.append(f"参考文献仅 {len(bibitems)} 篇，少于 15 篇要求")

        en_count = 0
        for m in re.finditer(r'\\bibitem\{[^}]+\}\s*(.*?)(?=\\bibitem|$)', self.tex_content, re.DOTALL):
            entry = m.group(1).strip()
            ascii_letters = len(re.findall(r'[a-zA-Z]', entry))
            chinese = len(re.findall(r'[\u4e00-\u9fff]', entry))
            if (ascii_letters + chinese) > 0 and ascii_letters / (ascii_letters + chinese) > 0.5:
                if len(re.findall(r'[a-zA-Z]{4,}', entry)) >= 3:
                    en_count += 1

        if en_count < 5:
            issues.append(f"英文文献仅 {en_count} 篇，少于 5 篇要求")

        pending = re.findall(r'待验证|待查证|DOI待验证', self.tex_content)
        if pending:
            issues.append(f"发现 {len(pending)} 处未处理的'待验证'标注")

        self.results['reference'] = {
            'status': len(issues) == 0,
            'issues': issues,
            'stats': {'total': len(bibitems), 'cited': len(cite_keys & bib_set),
                      'uncited': len(bib_set - cite_keys), 'unresolved': len(cite_keys - bib_set),
                      'en_refs': en_count, 'pending': len(pending)}
        }
        return self.results['reference']

    # ================================================================
    # 执行全部验证并生成报告
    # ================================================================
    def run_all(self) -> Dict:
        print("正在执行代码-论文一致性验证...")
        print(f"  论文: {self.tex_path}")
        print(f"  代码: {self.code_dir}")
        print(f"  日志: {self.log_dir}\n")

        for i, (name, method) in enumerate([
            ('数值结果一致性', self.verify_numerical),
            ('图表数据一致性', self.verify_figure_table),
            ('代码完整性', self.verify_code_integrity),
            ('公式一致性', self.verify_formula),
            ('参考文献可追溯性', self.verify_reference),
        ], 1):
            result = method()
            icon = '✅' if result['status'] else '❌'
            print(f"  [{i}/5] {name}: {icon}")
        print()
        return self.results

    def generate_report(self) -> str:
        lines = ["=" * 70, "          代码-论文一致性验证总报告", "=" * 70, ""]
        lines.append(f"{'验证项':<20} {'状态':<10} {'问题数':<10}")
        lines.append("-" * 70)
        all_pass = True
        for key, label in [
            ('numerical', '数值结果一致性'),
            ('figure_table', '图表数据一致性'),
            ('code_integrity', '代码完整性'),
            ('formula', '公式一致性'),
            ('reference', '参考文献可追溯性'),
        ]:
            r = self.results.get(key, {})
            status = '✅ 通过' if r.get('status') else '❌ 失败'
            if not r.get('status'):
                all_pass = False
            n = len(r.get('issues', []))
            lines.append(f"{label:<18} {status:<10} {n:<10}")
        lines.append("-" * 70)

        for key, label in [
            ('numerical', '数值结果一致性'),
            ('figure_table', '图表数据一致性'),
            ('code_integrity', '代码完整性'),
            ('formula', '公式一致性'),
            ('reference', '参考文献可追溯性'),
        ]:
            r = self.results.get(key, {})
            if r.get('issues'):
                lines.append(f"\n【{label}】问题详情：")
                for i, issue in enumerate(r['issues'], 1):
                    lines.append(f"  {i}. {issue}")

        lines.append(f"\n{'=' * 70}")
        if all_pass:
            lines.append("✅ 一致性验证全部通过，可以提交")
        else:
            failed = [k for k, v in self.results.items() if not v.get('status')]
            lines.append(f"⛔ {len(failed)} 项验证失败，禁止提交！失败项: {', '.join(failed)}")
        lines.append("=" * 70)
        return '\n'.join(lines)


if __name__ == '__main__':
    # Windows GBK 控制台/管道加固：报告含 emoji，重定向时防 UnicodeEncodeError
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    import argparse
    parser = argparse.ArgumentParser(description='代码-论文一致性验证')
    parser.add_argument('--tex', required=True, help='LaTeX 论文文件路径')
    parser.add_argument('--code_dir', required=True, help='代码目录路径')
    parser.add_argument('--log_dir', required=True, help='代码输出日志目录')
    args = parser.parse_args()

    verifier = ConsistencyVerifier(args.tex, args.code_dir, args.log_dir)
    verifier.run_all()
    report = verifier.generate_report()
    print(report)

    report_path = Path(args.log_dir) / 'consistency_report.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n报告已保存至: {report_path}")

    all_pass = all(v.get('status') for v in verifier.results.values())
    sys.exit(0 if all_pass else 1)
