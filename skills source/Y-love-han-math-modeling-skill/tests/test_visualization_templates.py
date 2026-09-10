from __future__ import annotations

import json
from pathlib import Path

import pytest

from templates.visualization import (
    architecture,
    data_overview,
    data_processing,
    model_result,
    sensitivity,
    validation,
)


@pytest.fixture()
def structured_input(tmp_path: Path) -> dict:
    return {
        "question_id": "Q1",
        "role": "model_result",
        "backend": "python",
        "input_artifact_ids": ["art_data"],
        "input_sha256": {"art_data": "a" * 64},
        "units": {"x": "time (d)", "y": "score (unit)"},
        "uncertainty_description": "95% bootstrap interval",
        "sample_size": 20,
        "x": list(range(20)),
        "y": [1.0 + 0.1 * i for i in range(20)],
        "lower": [0.9 + 0.1 * i for i in range(20)],
        "upper": [1.1 + 0.1 * i for i in range(20)],
        "paper_locator": "section:results;figure:1",
        "rendering_audit_id": "audit_render",
    }


@pytest.mark.parametrize(
    "module",
    [data_overview, data_processing, model_result, validation, sensitivity, architecture],
)
def test_python_template_generates_png_and_sidecar(module, structured_input, tmp_path):
    if module is architecture:
        structured_input = {
            **structured_input,
            "nodes": [
                {"id": "data", "label": "data", "x": 0, "y": 0},
                {"id": "model", "label": "model", "x": 1, "y": 0},
            ],
            "edges": [{"source": "data", "target": "model"}],
        }
    result = module.generate(structured_input, tmp_path / module.__name__.split(".")[-1])
    image = Path(result["image_path"])
    sidecar = Path(result["sidecar_path"])
    assert image.is_file() and image.stat().st_size > 1000
    assert sidecar.is_file()
    payload = json.loads(sidecar.read_text("utf-8"))
    assert payload["schema"] == "mmflow-figure-sidecar/v2"
    assert payload["question_id"] == "Q1"
    assert payload["backend"] == "python"
    assert payload["input_artifact_ids"] == ["art_data"]
    assert payload["image_sha256"]


def test_demo_input_is_rejected(structured_input, tmp_path):
    structured_input["artifact_class"] = "demo"
    with pytest.raises(ValueError, match="production"):
        data_overview.generate(structured_input, tmp_path / "bad")
