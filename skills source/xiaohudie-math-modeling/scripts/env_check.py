# -*- coding: utf-8 -*-
"""环境自检脚本 —— 数学建模技能第一步运行。

用法：
    python env_check.py

只检查、不安装。输出 OK/MISS 清单与对应平台的安装命令。
"""
import importlib
import shutil
import sys

PY_PKGS = [
    ("numpy", "numpy", "数值计算"),
    ("pandas", "pandas", "数据处理"),
    ("matplotlib", "matplotlib", "图表生成"),
    ("scipy", "scipy", "优化求解/统计"),
    ("sklearn", "scikit-learn", "机器学习"),
    ("statsmodels", "statsmodels", "时序模型 ARIMA"),
    ("openpyxl", "openpyxl", "读写 Excel 附件"),
    ("chardet", "chardet", "编码探测"),
]

CMDS = [
    ("xelatex", "论文编译（LaTeX 主路径）"),
    ("typst", "论文编译（轻量备选）"),
    ("pandoc", "Markdown→docx 降级"),
    ("pdftoppm", "PDF 转 PNG 视觉检查"),
]

INSTALL_HINTS = {
    "xelatex": "Windows: winget install MiKTeX.MiKTeX   （精简替代：TeX Live 的 texlive-xetex + texlive-lang-chinese）",
    "typst": "Windows: winget install Typst.Typst",
    "pandoc": "Windows: winget install JohnMacFarlane.Pandoc   或 pip install pypandoc-binary",
    "pdftoppm": "Windows: winget install oschwartz10612.Poppler",
}


def main():
    print("=" * 64)
    print("数学建模技能环境自检")
    print("=" * 64)
    print(f"Python {sys.version.split()[0]}  ({sys.executable})")
    print("-" * 64)

    missing_pkgs = []
    for mod, dist, purpose in PY_PKGS:
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "?")
            print(f"OK    {dist:<14} {ver:<10} {purpose}")
        except ImportError:
            print(f"MISS  {dist:<14} {'-':<10} {purpose}")
            missing_pkgs.append(dist)

    print("-" * 64)
    missing_cmds = []
    for cmd, purpose in CMDS:
        where = shutil.which(cmd)
        if where:
            print(f"OK    {cmd:<10} {where}")
        else:
            print(f"MISS  {cmd:<10} {purpose}")
            missing_cmds.append(cmd)

    print("-" * 64)
    # 必须项判定
    hard = []
    for dist in ("numpy", "pandas", "matplotlib"):
        if dist in missing_pkgs:
            hard.append(dist)
    if missing_pkgs:
        print("pip install " + " ".join(missing_pkgs))
    for cmd in missing_cmds:
        print(INSTALL_HINTS[cmd])

    if hard:
        print(f"\n[结论] 缺少必须 Python 包：{hard} —— 求解阶段无法开始")
    elif "xelatex" in missing_cmds and "typst" in missing_cmds:
        print("\n[结论] 求解可进行；论文将走 Markdown→docx 降级路径（建议安装 xelatex 出正式 PDF）")
    else:
        print("\n[结论] 环境就绪，可走完整 LaTeX 流程")


if __name__ == "__main__":
    main()
