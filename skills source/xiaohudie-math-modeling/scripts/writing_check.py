# -*- coding: utf-8 -*-
"""论文质检脚本 —— 编译后的文本质量门禁（移植自 MathModelAgent writing_check.sh 思想，跨平台 Python 版）。

用法：
    python writing_check.py <论文目录> [--main 主tex名] [--compile]

不带 --compile 时只做静态检查（要求已编译过、.log/.aux 存在）；
带 --compile 且本机有 xelatex 时自动连编两遍再检查。

检查项（FAIL 为硬错误，必须修复后重跑）：
  1. 编译 Error 计数          5. \\includegraphics 引用的图片存在
  2. Overfull/Float too large 6. \\cite 与 \\bibitem 一一对应
  3. 交叉引用未解析（??）      7. 摘要一页校验（aux 中 abstract:end 页码）
  4. 占位符残留                8. PDF 存在且非空
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys

PLACEHOLDER_PATTERNS = ["TODO", "PLACEHOLDER", "待补充", "待续写", "示例数据", "【", "】"]


def find_tex_files(paper_dir):
    return [p for p in glob.glob(os.path.join(paper_dir, "**", "*.tex"), recursive=True)
            if not os.path.basename(p).startswith("5.1.1") or True]


def check(paper_dir, main_name=None):
    results = []  # (级别, 编号, 说明)  级别: PASS/WARN/FAIL

    main_tex = None
    if main_name:
        cand = os.path.join(paper_dir, main_name)
        if os.path.isfile(cand):
            main_tex = cand
    if main_tex is None:
        for name in ("论文.tex", "main.tex"):
            cand = os.path.join(paper_dir, name)
            if os.path.isfile(cand):
                main_tex = cand
                break
    if main_tex is None:
        texs = glob.glob(os.path.join(paper_dir, "*.tex"))
        main_tex = texs[0] if texs else None
    if main_tex is None:
        return [("FAIL", "0", f"论文目录中找不到主 tex 文件：{paper_dir}")], main_tex
    results.append(("PASS", "0", f"主文件：{os.path.basename(main_tex)}"))

    # 1. 编译 Error 计数
    log_path = os.path.splitext(main_tex)[0] + ".log"
    if os.path.isfile(log_path):
        log = open(log_path, "rb").read().decode("utf-8", errors="replace")
        n_err = len(re.findall(r"^! |.*:\d+: .*Error", log, flags=re.M)) + log.count("LaTeX Error")
        results.append(("PASS" if n_err == 0 else "FAIL", "1", f"编译 Error 计数 = {n_err}"))
        # 2. Overfull / Float too large
        over = re.findall(r"(Overfull \\hbox[^\n]*|Overfull \\vbox[^\n]*|Float too large[^\n]*)", log)
        results.append(("PASS" if not over else "WARN", "2",
                        f"Overfull/Float too large = {len(over)} 条" + (f"；首条：{over[0][:80]}" if over else "")))
        # 3. 交叉引用未解析
        n_undef = log.count("undefined references") + log.count("Reference .* undefined")
        n_qq = len(re.findall(r"\?\?", log))
        results.append(("PASS" if n_undef == 0 and n_qq == 0 else "WARN",
                        "3", f"未解析引用提示 {n_undef} 条；log 中 '??' {n_qq} 次"))
    else:
        results.append(("WARN", "1", "未找到 .log（尚未编译；可加 --compile 让本脚本代跑）"))

    # 4. 占位符残留（扫描正文 tex；跳过注释行）
    all_tex = find_tex_files(paper_dir)
    found_ph = []
    for tex in all_tex:
        for i, line in enumerate(open(tex, encoding="utf-8", errors="replace"), 1):
            stripped = line.split("%", 1)[0]
            for pat in PLACEHOLDER_PATTERNS:
                if pat in stripped:
                    found_ph.append(f"{os.path.basename(tex)}:{i}:{pat}")
    results.append(("PASS" if not found_ph else "FAIL", "4",
                    "占位符残留 0 处" if not found_ph else f"占位符 {len(found_ph)} 处：{found_ph[:8]}"))

    # 5. includegraphics 图片存在性（跳过注释行）
    missing_imgs = []
    for tex in all_tex:
        base = os.path.dirname(tex)
        text = "\n".join(line.split("%", 1)[0]
                         for line in open(tex, encoding="utf-8", errors="replace"))
        for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", text):
            img = m.group(1).strip()
            if img.startswith("http"):
                continue
            cands = [img, img + ".pdf", img + ".png", img + ".jpg", img + ".eps"]
            if not any(os.path.isfile(os.path.join(base, c)) for c in cands):
                missing_imgs.append(f"{os.path.basename(tex)}:{img}")
    results.append(("PASS" if not missing_imgs else "FAIL", "5",
                    "图片引用全部存在" if not missing_imgs else f"缺失图片 {len(missing_imgs)}：{missing_imgs[:8]}"))

    # 6. cite / bibitem 对应（跳过注释行）
    cites, bibs = set(), set()
    for tex in all_tex:
        text = "\n".join(line.split("%", 1)[0]
                         for line in open(tex, encoding="utf-8", errors="replace"))
        for m in re.finditer(r"\\cite\{([^}]+)\}", text):
            for k in m.group(1).split(","):
                cites.add(k.strip())
        for m in re.finditer(r"\\bibitem\{([^}]+)\}", text):
            bibs.add(m.group(1).strip())
    bibs = {b for b in bibs if b not in ("标签", "ref1", "ref2", "ref3")}
    uncited = bibs - cites
    missing_bib = cites - bibs
    ok = not uncited and not missing_bib
    msg = f"cite {len(cites)} 条 / bibitem {len(bibs)} 条"
    if uncited:
        msg += f"；未被引用的 bibitem：{sorted(uncited)[:6]}"
    if missing_bib:
        msg += f"；cite 无对应条目：{sorted(missing_bib)[:6]}"
    results.append(("PASS" if ok else "FAIL", "6", msg))

    # 7. 摘要一页校验
    aux_path = os.path.splitext(main_tex)[0] + ".aux"
    if os.path.isfile(aux_path):
        aux = open(aux_path, encoding="utf-8", errors="replace").read()
        m = re.search(r"newlabel\{abstract:end\}.*?\{(\d+)\}", aux)
        if m:
            page = int(m.group(1))
            results.append(("PASS" if page <= 1 else "FAIL", "7", f"摘要结束页码 = {page}（要求 ≤1）"))
        else:
            results.append(("WARN", "7", "aux 中未找到 abstract:end 标签（模板未加或摘要环境不同）"))
    else:
        results.append(("WARN", "7", "未找到 .aux，跳过摘要一页校验"))

    # 8. PDF 存在且非空
    pdf_path = os.path.splitext(main_tex)[0] + ".pdf"
    if os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 10_000:
        results.append(("PASS", "8", f"PDF 存在：{os.path.getsize(pdf_path)} bytes"))
    elif os.path.isfile(pdf_path):
        results.append(("FAIL", "8", f"PDF 过小（{os.path.getsize(pdf_path)} bytes），疑似编译失败"))
    else:
        results.append(("FAIL", "8", "PDF 不存在"))

    return results, main_tex


def compile_twice(main_tex):
    if not shutil.which("xelatex"):
        print("[compile] 本机无 xelatex，跳过编译")
        return
    d = os.path.dirname(main_tex)
    name = os.path.basename(main_tex)
    for i in (1, 2):
        print(f"[compile] 第 {i} 遍 xelatex ...")
        subprocess.run(["xelatex", "-interaction=nonstopmode", name],
                       cwd=d, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paper_dir")
    ap.add_argument("--main", default=None, help="主 tex 文件名（默认自动找 论文.tex/main.tex）")
    ap.add_argument("--compile", action="store_true", help="先自动 xelatex 编译两遍再检查")
    args = ap.parse_args()

    if args.compile:
        guess = os.path.join(args.paper_dir, args.main or "论文.tex")
        if os.path.isfile(guess):
            compile_twice(guess)
        else:
            guess2 = os.path.join(args.paper_dir, args.main or "main.tex")
            if os.path.isfile(guess2):
                compile_twice(guess2)

    results, main_tex = check(args.paper_dir, args.main)
    print("=" * 64)
    print(f"论文质检报告：{args.paper_dir}")
    print("=" * 64)
    n_fail = 0
    for level, no, msg in results:
        print(f"{level:<5} [{no}] {msg}")
        if level == "FAIL":
            n_fail += 1
    verdict = "PASS" if n_fail == 0 else "FAIL"
    print("-" * 64)
    print(f"结论：{verdict}（FAIL {n_fail} 项——硬错误必须修复后重跑）")

    # 写报告
    out_dir = os.path.join(os.path.dirname(args.paper_dir.rstrip("/\\")), "检查")
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "VERIFY_REPORT.md"), "w", encoding="utf-8") as f:
            f.write(f"# 论文质检报告\n\n- 目录：{args.paper_dir}\n- 结论：**{verdict}**\n\n")
            f.write("| 级别 | 编号 | 说明 |\n|---|---|---|\n")
            for level, no, msg in results:
                f.write(f"| {level} | {no} | {msg.replace('|', '/')} |\n")
        print(f"报告已写入：{os.path.join(out_dir, 'VERIFY_REPORT.md')}")
    except OSError:
        pass
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
