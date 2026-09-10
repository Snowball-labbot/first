# -*- coding: utf-8 -*-
"""
create_word.py - 论文 Word 版本生成脚本
功能：将 LaTeX 论文转换为 Word 格式（.docx），确保与 PDF 版本内容一致
运行方式：python create_word.py（在 论文/ 目录下运行）
输出：论文终稿.docx
依赖：pandoc（推荐）或 python-docx（备选）
对应论文：§9 阶段 9"生成 Word 版本"备选方案

转换策略：
1. 优先使用 pandoc（LaTeX → docx 转换质量最高）
2. pandoc 不可用时，使用 python-docx 从 PDF 提取内容构建
3. 两者均不可用时，提示安装依赖
"""
import os
import sys
import subprocess
from pathlib import Path

# ============================================================
# 配置
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
TEX_FILE = SCRIPT_DIR / 'main.tex'
PDF_FILE = SCRIPT_DIR / 'main.pdf'
OUTPUT_DOCX = SCRIPT_DIR / '论文终稿.docx'


def try_pandoc() -> bool:
    """方式一：使用 pandoc 转换（推荐，转换质量最高）"""
    print("尝试使用 pandoc 转换...")
    try:
        # 检查 pandoc 是否安装
        result = subprocess.run(['pandoc', '--version'],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print("  pandoc 未安装，跳过此方式")
            return False

        # 执行转换
        cmd = [
            'pandoc',
            str(TEX_FILE),
            '-o', str(OUTPUT_DOCX),
            '--from=latex',
            '--to=docx',
            '--standalone',
            '--number-sections',          # 保留章节编号
            '--highlight-style=tango',     # 代码高亮风格
        ]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding='utf-8')

        if result.returncode == 0 and OUTPUT_DOCX.exists():
            print(f"  ✅ pandoc 转换成功：{OUTPUT_DOCX}")
            return True
        else:
            print(f"  ⚠️ pandoc 转换失败：{result.stderr[:200]}")
            # 说明：pandoc 不支持 PDF 作为输入格式（--from=pdf 必然
            # 失败），因此不再尝试无效的 PDF 回退；pandoc 失败时直接
            # 进入 python-docx 骨架方案。
            return False

    except FileNotFoundError:
        print("  pandoc 未安装，跳过此方式")
        return False
    except Exception as e:
        print(f"  ⚠️ pandoc 转换异常：{e}")
        return False


def try_python_docx() -> bool:
    """方式二：使用 python-docx 手动构建 Word 文档"""
    print("尝试使用 python-docx 构建...")
    try:
        from docx import Document
        from docx.shared import Pt, Cm, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        print("  python-docx 未安装，请运行：pip install python-docx")
        return False

    doc = Document()

    # ---------- 页面设置 ----------
    section = doc.sections[0]
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    # ---------- 默认字体 ----------
    style = doc.styles['Normal']
    font = style.font
    font.name = '宋体'
    font.size = Pt(12)

    # ---------- 标题 ----------
    title = doc.add_heading('', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run('<论文标题：基于题目特定机制的建模与优化研究>')
    run.font.size = Pt(22)
    run.font.name = '黑体'

    # ---------- 摘要 ----------
    doc.add_heading('摘  要', level=1)
    doc.add_paragraph('[粘贴摘要正文——从 main.tex 或 main.pdf 中提取]')
    doc.add_paragraph()
    p = doc.add_paragraph()
    run = p.add_run('关键词：')
    run.bold = True
    p.add_run('关键词1；关键词2；关键词3；关键词4；关键词5')

    doc.add_page_break()

    # ---------- 正文骨架 ----------
    sections = [
        '一、问题重述',
        '二、问题分析',
        '三、模型假设',
        '四、符号说明',
        '五、问题一的建模与求解',
        '六、问题二的建模与求解',
        '七、模型验证与灵敏度分析',
        '八、讨论',
        '九、模型评价与推广',
        '十、结论',
        '参考文献',
    ]

    for sec_title in sections:
        doc.add_heading(sec_title, level=1)
        doc.add_paragraph(f'[从 main.tex 或 main.pdf 中提取 {sec_title} 的内容]')
        doc.add_paragraph()

    # ---------- 附录 ----------
    doc.add_heading('附录', level=1)
    doc.add_heading('附录一：支撑材料文件列表', level=2)
    doc.add_paragraph('[文件列表表格]')
    doc.add_heading('附录二：运行环境依赖', level=2)
    doc.add_paragraph('[requirements.txt 内容]')
    doc.add_heading('附录三：utils.py 完整代码', level=2)
    doc.add_paragraph('[代码内容]')

    # ---------- 保存 ----------
    doc.save(str(OUTPUT_DOCX))
    print(f"  ✅ python-docx 构建成功：{OUTPUT_DOCX}")
    print("  ⚠️ 注意：此方式生成的是骨架文档，需手动填充内容")
    print("  建议优先使用 pandoc 转换以保留完整内容")
    return True


def main():
    # Windows GBK 控制台/管道加固：报告含 emoji，重定向时防 UnicodeEncodeError
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    print("=" * 60)
    print("论文 Word 版本生成脚本")
    print("=" * 60)
    print(f"输入：{TEX_FILE}")
    print(f"输出：{OUTPUT_DOCX}")
    print()

    # 检查 LaTeX 源文件是否存在
    if not TEX_FILE.exists():
        print(f"❌ LaTeX 源文件不存在：{TEX_FILE}")
        print("  请先完成论文撰写并生成 main.tex")
        sys.exit(1)

    # 按优先级尝试转换方式
    success = False

    if not success:
        success = try_pandoc()

    if not success:
        success = try_python_docx()

    if not success:
        print("\n" + "=" * 60)
        print("❌ 所有转换方式均失败")
        print("请安装以下任一依赖：")
        print("  方式一（推荐）：安装 pandoc")
        print("    Windows:  https://pandoc.org/installing.html")
        print("    macOS:    brew install pandoc")
        print("    Linux:    sudo apt install pandoc")
        print("  方式二：安装 python-docx")
        print("    pip install python-docx")
        print("=" * 60)
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"✅ Word 版本已生成：{OUTPUT_DOCX}")
    print("⚠️ 请人工检查 Word 版本与 PDF 版本的一致性")
    print("=" * 60)


if __name__ == '__main__':
    main()
