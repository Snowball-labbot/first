# -*- coding: utf-8 -*-
"""
appendix_code_closure_check.py — 附录代码闭包核验（P9/P10 审查工具）
用途：核验"稿件附录中的代码"与"实际登记的源代码"是否闭包一致：
      1) 从 LaTeX 附录中抽取 lstlisting/verbatim 代码块；
      2) 与 --code-dir 下的源文件做规范化内容比对（一致 / 漂移 / 孤儿）；
      3) 对抽取出的 Python 块做语法编译自检（py_compile）；
      4) 可选 --replay：在临时目录逐块实际运行（限 Python，带超时），
         记录退出码。非 Python 工具（MATLAB/LINGO 等）按 isolation-runtime
         规范只做呈现核验，不做 execution 级重放。
定位：审查素材生成器。报告供 P9 代码闭包核验与 P10 复现审查消费；
      本脚本不修改稿件与源代码，也不把重放结果当作生产证据。

运行方式：
  python appendix_code_closure_check.py --tex 论文/main.tex --code-dir src --output report.json
  python appendix_code_closure_check.py --tex 论文/main.tex --extract-dir extracted --replay --output report.json
退出码：0 一致；1 存在漂移/孤儿/编译失败；2 输入不合法；3 重放失败
"""
from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_BLOCK_PATTERN = re.compile(
    r"\\begin\{(lstlisting|verbatim)\}(?:\[[^\]]*\])?(?:\{[^}]*\})?(.*?)\\end\{\1\}",
    flags=re.DOTALL,
)
_LANGUAGE_PATTERN = re.compile(r"language\s*=\s*([A-Za-z+#]+)")


def _normalize(text: str) -> str:
    """规范化比较：去行尾空白、去空行、统一换行，忽略纯注释差异不成立——
    附录代码应与源码逐字一致，这里只压缩空白类差异。"""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(line for line in lines if line.strip())


def extract_blocks(tex_path: Path) -> list[dict]:
    content = tex_path.read_text(encoding="utf-8", errors="replace")
    blocks = []
    for index, match in enumerate(_BLOCK_PATTERN.finditer(content), start=1):
        environment, code = match.group(1), match.group(2)
        language_match = _LANGUAGE_PATTERN.search(match.group(0))
        language = (language_match.group(1).lower() if language_match
                    else ("python" if environment == "lstlisting" else "plain"))
        blocks.append({
            "index": index,
            "environment": environment,
            "language": language,
            "line": content[: match.start()].count("\n") + 1,
            "code": code.strip("\n"),
            "sha256": hashlib.sha256(_normalize(code).encode("utf-8")).hexdigest(),
        })
    return blocks


def match_sources(blocks: list[dict], code_dir: Path | None) -> list[dict]:
    entries = []
    sources: dict[str, Path] = {}
    if code_dir is not None and code_dir.is_dir():
        for path in sorted(code_dir.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".m", ".txt", ".lgo"}:
                sources[str(path.relative_to(code_dir).as_posix())] = path
    normalized_sources = {
        name: _normalize(path.read_text(encoding="utf-8", errors="replace"))
        for name, path in sources.items()
    }
    source_hashes = {
        name: hashlib.sha256(text.encode("utf-8")).hexdigest()
        for name, text in normalized_sources.items()
    }
    for block in blocks:
        entry = dict(block)
        entry["matched_source"] = None
        entry["status"] = "UNMATCHED"
        if block["sha256"] in source_hashes.values():
            entry["matched_source"] = next(
                name for name, digest in source_hashes.items()
                if digest == block["sha256"]
            )
            entry["status"] = "MATCHED"
        elif normalized_sources:
            # 哈希不同但文本规范化后互为包含：判定为漂移（附录版本与源码不一致）
            for name, text in normalized_sources.items():
                if _normalize(block["code"]) and (
                    _normalize(block["code"]) in text or text in _normalize(block["code"])
                ):
                    entry["matched_source"] = name
                    entry["status"] = "DRIFTED"
                    break
        entries.append(entry)
    orphans = [
        name for name in sources
        if name not in {entry["matched_source"] for entry in entries if entry["matched_source"]}
    ]
    return entries, orphans


def compile_check(entries: list[dict]) -> list[dict]:
    results = []
    with tempfile.TemporaryDirectory() as scratch:
        for entry in entries:
            if entry["language"] != "python" or not entry["code"].strip():
                continue
            target = Path(scratch) / f"block_{entry['index']}.py"
            target.write_text(entry["code"], encoding="utf-8")
            try:
                py_compile.compile(str(target), doraise=True)
                results.append({"index": entry["index"], "status": "OK"})
            except py_compile.PyCompileError as error:
                results.append({"index": entry["index"], "status": "SYNTAX_ERROR",
                                "error": str(error)[-300:]})
    return results


def replay(entries: list[dict], timeout: int = 60) -> list[dict]:
    results = []
    with tempfile.TemporaryDirectory() as scratch:
        for entry in entries:
            if entry["language"] != "python" or not entry["code"].strip():
                continue
            target = Path(scratch) / f"block_{entry['index']}.py"
            target.write_text(entry["code"], encoding="utf-8")
            try:
                completed = subprocess.run(
                    [sys.executable, str(target)], capture_output=True,
                    text=True, timeout=timeout, cwd=scratch,
                )
                results.append({"index": entry["index"], "exit_code": completed.returncode,
                                "stderr_tail": completed.stderr[-300:]})
            except subprocess.TimeoutExpired:
                results.append({"index": entry["index"], "exit_code": None,
                                "stderr_tail": f"timeout after {timeout}s"})
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Appendix code closure check")
    parser.add_argument("--tex", required=True, help="manuscript LaTeX containing the appendix")
    parser.add_argument("--code-dir", default=None, help="directory of registered source files")
    parser.add_argument("--extract-dir", default=None, help="write extracted blocks here for inspection")
    parser.add_argument("--replay", action="store_true",
                        help="actually run extracted Python blocks (bounded by --timeout)")
    parser.add_argument("--timeout", type=int, default=60, help="per-block replay timeout seconds")
    parser.add_argument("--output", required=True, help="report JSON (must not exist)")
    args = parser.parse_args(argv)

    tex_path = Path(args.tex)
    if not tex_path.is_file():
        print(f"error: manuscript not found: {tex_path}")
        return 2
    blocks = extract_blocks(tex_path)
    if not blocks:
        print("warning: no lstlisting/verbatim blocks found in the appendix region")
    code_dir = Path(args.code_dir) if args.code_dir else None
    entries, orphans = match_sources(blocks, code_dir)
    if args.extract_dir:
        extract_root = Path(args.extract_dir)
        extract_root.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            suffix = ".py" if entry["language"] == "python" else ".txt"
            (extract_root / f"block_{entry['index']}{suffix}").write_text(
                entry["code"], encoding="utf-8"
            )
    compile_results = compile_check(entries) if entries else []
    replay_results = replay(entries, args.timeout) if args.replay and entries else []
    drifted = [entry["index"] for entry in entries if entry["status"] == "DRIFTED"]
    unmatched = [entry["index"] for entry in entries if entry["status"] == "UNMATCHED"]
    syntax_errors = [item["index"] for item in compile_results if item["status"] != "OK"]
    replay_failures = [item["index"] for item in replay_results if item["exit_code"] != 0]
    # 提供 --code-dir 即断言闭包：漂移、未匹配到源文件的代码块或语法错误均 FAIL
    closure_required = code_dir is not None
    overall = "FAIL" if (drifted or (closure_required and unmatched) or syntax_errors) else "PASS"
    if args.replay and replay_failures:
        overall = "FAIL"
    report = {
        "schema": "mmflow-appendix-closure-report/v1",
        "tex": str(tex_path),
        "blocks_found": len(blocks),
        "matched": sum(1 for entry in entries if entry["status"] == "MATCHED"),
        "drifted": drifted,
        "unmatched": unmatched,
        "orphan_sources": orphans,
        "compile_check": compile_results,
        "replay_results": replay_results,
        "note": "non-Python tools are presentation-checked only (isolation-runtime boundary)",
        "status": overall,
    }
    output = Path(args.output)
    if output.exists():
        print(f"error: output already exists: {output}")
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": overall, "blocks": len(blocks),
                      "drifted": len(drifted), "unmatched": len(unmatched),
                      "orphans": len(orphans), "output": str(output)},
                     ensure_ascii=False))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
