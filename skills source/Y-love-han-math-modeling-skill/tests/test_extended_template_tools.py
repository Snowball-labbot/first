from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SKILL_ROOT / script), *args],
        capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# analytics: cv_backtest / convergence_scan / evaluation_checks
# ---------------------------------------------------------------------------


def test_cv_backtest_group_kfold_is_leak_free(tmp_path):
    spec = {
        "mode": "group_kfold",
        "groups": ["g1", "g1", "g2", "g2", "g3", "g3", "g4", "g4", "g5", "g5"],
        "k": 5,
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    output = tmp_path / "report.json"
    completed = _run(
        "templates/analytics/cv_backtest.py",
        "--spec", str(spec_path), "--output", str(output),
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "PASS" and len(report["splits"]) == 5
    for split in report["splits"]:
        assert not set(split["train"]) & set(split["validation"])


def test_cv_backtest_refuses_existing_output(tmp_path):
    spec = {"mode": "kfold", "n_samples": 50, "k": 5}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    output = tmp_path / "report.json"
    assert _run("templates/analytics/cv_backtest.py", "--spec", str(spec_path),
                "--output", str(output)).returncode == 0
    assert _run("templates/analytics/cv_backtest.py", "--spec", str(spec_path),
                "--output", str(output)).returncode == 2


def test_convergence_scan_estimates_second_order(tmp_path):
    payload = {
        "steps": [0.1, 0.05, 0.025, 0.0125],
        "values": [1.0243, 1.0061, 1.0015, 1.0004],
        "tolerance": 1e-3,
        "expected_order": 2,
    }
    input_path = tmp_path / "conv.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "report.json"
    completed = _run(
        "templates/analytics/convergence_scan.py",
        "--input", str(input_path), "--output", str(output),
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    # 数据按 O(h^2) 生成：观测阶必须接近 2
    assert abs(report["observed_order"] - 2.0) < 0.2
    # final_gap 略高于容差时判定 FAIL，返回码非零
    assert report["status"] == "FAIL" and completed.returncode == 1


def test_evaluation_checks_ahp_topsis(tmp_path):
    payload = {
        "ahp": {"matrix": [[1, 3, 5], [1 / 3, 1, 3], [1 / 5, 1 / 3, 1]]},
        "topsis": {
            "matrix": [[8, 2, 500], [9, 3, 600], [6, 1, 450]],
            "directions": ["max", "max", "min"],
            "weights": [0.5, 0.3, 0.2],
            "weight_perturbations": [0.05, 0.1],
            "claimed_best": 0,
        },
    }
    input_path = tmp_path / "eval.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "report.json"
    completed = _run(
        "templates/analytics/evaluation_checks.py",
        "--input", str(input_path), "--output", str(output),
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["checks"]["ahp_consistency"]["CR"] < 0.1
    assert report["checks"]["domination_check"]["status"] == "PASS"


# ---------------------------------------------------------------------------
# quality: redteam_claim_drill / appendix_code_closure_check
# ---------------------------------------------------------------------------

_CLAIMS = {
    "schema": "mmflow-defense-cards-input/v1",
    "competition": "CUMCM",
    "claims": [
        {
            "claim_id": "C-01",
            "statement": "模型给出的路径为全局最优，总成本 128.5 元",
            "supporting_result_ids": ["R-01"],
            "formula_ids": [],
            "citation_ids": [],
            "limitations": ["以精确求解器证书为前提"],
        },
        {
            "claim_id": "C-02",
            "statement": "预测准确率 92.3%，显著优于基线",
            "supporting_result_ids": ["R-02"],
            "formula_ids": [],
            "citation_ids": [],
            "limitations": [],
        },
    ],
}


def test_redteam_claim_drill_builds_checklist(tmp_path):
    claims_path = tmp_path / "claims.json"
    claims_path.write_text(json.dumps(_CLAIMS, ensure_ascii=False), encoding="utf-8")
    md = tmp_path / "surface.md"
    js = tmp_path / "surface.json"
    completed = _run(
        "templates/quality/redteam_claim_drill.py",
        "--claims", str(claims_path),
        "--output-md", str(md), "--output-json", str(js),
    )
    assert completed.returncode == 0, completed.stderr
    text = md.read_text(encoding="utf-8")
    payload = json.loads(js.read_text(encoding="utf-8"))
    # 最优性证书与数据泄漏两类攻击必须被关键词命中
    assert "最优性证书" in text and "数据泄漏" in text
    # 多类别命中（如 预测+显著 → 数据泄漏+稳健性）标记为 HIGH
    assert any(item["risk_priority"] == "HIGH" for item in payload["surface"])


def test_appendix_closure_detects_drift(tmp_path):
    tex = tmp_path / "main.tex"
    tex.write_text(
        "\\begin{lstlisting}[language=Python]\nprint('v1')\n\\end{lstlisting}\n",
        encoding="utf-8",
    )
    code_dir = tmp_path / "src"
    code_dir.mkdir()
    (code_dir / "solution.py").write_text("print('v2')\n", encoding="utf-8")
    output = tmp_path / "closure.json"
    completed = _run(
        "templates/quality/appendix_code_closure_check.py",
        "--tex", str(tex), "--code-dir", str(code_dir), "--output", str(output),
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "FAIL"
    assert report["drifted"] or report["unmatched"]


def test_appendix_closure_passes_on_identical_code(tmp_path):
    tex = tmp_path / "main.tex"
    tex.write_text(
        "\\begin{lstlisting}[language=Python]\nprint('v1')\n\\end{lstlisting}\n",
        encoding="utf-8",
    )
    code_dir = tmp_path / "src"
    code_dir.mkdir()
    (code_dir / "solution.py").write_text("print('v1')\n", encoding="utf-8")
    output = tmp_path / "closure.json"
    completed = _run(
        "templates/quality/appendix_code_closure_check.py",
        "--tex", str(tex), "--code-dir", str(code_dir), "--output", str(output),
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "PASS" and report["matched"] == 1


# ---------------------------------------------------------------------------
# publication: build_abstract
# ---------------------------------------------------------------------------


def test_build_abstract_copies_numbers_verbatim(tmp_path):
    claims_path = tmp_path / "claims.json"
    claims_path.write_text(json.dumps(_CLAIMS, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "draft.md"
    completed = _run(
        "templates/publication/build_abstract.py",
        "--claims", str(claims_path), "--output", str(output),
    )
    assert completed.returncode == 0, completed.stderr
    draft = output.read_text(encoding="utf-8")
    assert "128.5" in draft and "92.3%" in draft
    assert "【待填:" in draft  # 未填槽位必须显式标记


# ---------------------------------------------------------------------------
# maintenance tools: heal_mismatch / auto_drive
# ---------------------------------------------------------------------------


def test_auto_drive_refuses_uninitialized_project(tmp_path):
    completed = _run("scripts/auto_drive.py", str(tmp_path), "g1")
    assert completed.returncode == 2
    assert "not initialized" in completed.stdout


def test_heal_mismatch_refuses_uninitialized_project(tmp_path):
    completed = _run("scripts/heal_mismatch.py", "--project", str(tmp_path))
    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
