from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "templates" / "analytics" / "problem_reference_implementation.py"
    spec = importlib.util.spec_from_file_location("problem_reference", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reference_implementation_runs_end_to_end(tmp_path):
    module = _load_module()
    data = module.make_reference_data()
    output = module.run_reference_pipeline(data, tmp_path)
    assert set(output) >= {"model", "theory", "results", "ablation", "uncertainty"}
    assert output["results"]["rmse"] >= 0
    assert output["ablation"]["status"] == "PASS"
    assert output["uncertainty"]["status"] == "PASS"
    saved = json.loads((tmp_path / "reference_results.json").read_text("utf-8"))
    assert saved["schema"] == "math-modeling-reference-result/v1"

