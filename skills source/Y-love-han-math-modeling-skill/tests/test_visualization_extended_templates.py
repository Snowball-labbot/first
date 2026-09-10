from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from templates.visualization import (
    bar_chart,
    convergence,
    distribution,
    generate_all,
    heatmap,
    model_diagram,
    network_graph,
    pareto,
    radar,
    residual_diagnosis,
    result_table,
    scatter_fit,
    spatial_map,
)

NEW_MODULES = [
    heatmap, distribution, radar, pareto, convergence,
    residual_diagnosis, network_graph, bar_chart, scatter_fit,
    result_table, model_diagram, spatial_map,
]


@pytest.fixture()
def base_input() -> dict:
    return {
        "question_id": "Q1",
        "input_artifact_ids": ["art_a"],
        "input_sha256": {"art_a": "a" * 64},
        "units": {"x": "x (m)", "y": "y (s)", "value": "v (kg)"},
        "sample_size": 12,
    }


@pytest.fixture()
def module_inputs(base_input: dict) -> dict:
    return {
        heatmap: {
            **base_input,
            "matrix": [[1.0, 0.5, -0.2], [0.5, 1.0, 0.3], [-0.2, 0.3, 1.0]],
            "row_labels": ["a", "b", "c"],
            "col_labels": ["a", "b", "c"],
        },
        distribution: {**base_input, "groups": {"g1": [1, 2, 3, 4], "g2": [2, 3, 4, 5]}},
        radar: {
            **base_input,
            "indicators": ["x1", "x2", "x3", "x4"],
            "series": {"A": [0.8, 0.6, 0.9, 0.5], "B": [0.6, 0.7, 0.4, 0.8]},
        },
        pareto: {**base_input, "points": [[1, 5], [2, 4], [3, 2], [4, 1], [2.5, 3.5]]},
        convergence: {
            **base_input,
            "h": [0.1, 0.05, 0.025, 0.0125],
            "error": [1e-2, 2.5e-3, 6.2e-4, 1.55e-4],
        },
        residual_diagnosis: {
            **base_input,
            "fitted": [1, 2, 3, 4, 5, 6],
            "residuals": [0.1, -0.2, 0.05, 0.3, -0.1, 0.02],
        },
        network_graph: {
            **base_input,
            "nodes": [{"id": "a", "value": 3}, {"id": "b", "value": 1}, {"id": "c"}],
            "edges": [
                {"source": "a", "target": "b", "weight": 2},
                {"source": "b", "target": "c"},
            ],
        },
        bar_chart: {
            **base_input,
            "categories": ["m1", "m2", "m3"],
            "series": {"A": [1, 2, 3], "B": [2, 1.5, 2.5]},
        },
        scatter_fit: {
            **base_input,
            "x": [1, 2, 3, 4],
            "y": [1.1, 1.9, 3.2, 3.8],
            "fit": {"slope": 0.92, "intercept": 0.13},
            "show_identity": True,
        },
        result_table: {
            **base_input,
            "columns": ["Model", "Error", "Time"],
            "rows": [["A", "0.12", "3s"], ["B", "0.08", "5s"], ["C", "0.20", "2s"]],
            "highlight_column": "Error",
        },
        model_diagram: {
            **base_input,
            "blocks": [
                {"id": "d", "label": "data"},
                {"id": "m", "label": "model", "stage": "2"},
                {"id": "v", "label": "validate", "stage": "3"},
            ],
            "flows": [
                {"source": "d", "target": "m"},
                {"source": "m", "target": "v", "label": "result"},
            ],
        },
        spatial_map: {
            **base_input,
            "points": [
                {"x": 1, "y": 2, "value": 0.5, "label": "P1"},
                {"x": 3, "y": 1, "value": 1.2},
                {"x": 2, "y": 3, "value": 0.8},
            ],
        },
    }


@pytest.mark.parametrize(
    "module", NEW_MODULES, ids=lambda module: module.__name__.split(".")[-1]
)
def test_extended_template_generates_png_and_sidecar(module, module_inputs, tmp_path):
    data = dict(module_inputs[module])
    if module.__name__.endswith("scatter_fit"):
        data.update(
            {
                "x": [1, 2, 3, 4],
                "y": [1.1, 1.9, 3.2, 3.8],
                "fit": {"slope": 0.92, "intercept": 0.13},
                "show_identity": True,
            }
        )
    result = module.generate(data, tmp_path / module.__name__.split(".")[-1])
    image = Path(result["image_path"])
    sidecar = Path(result["sidecar_path"])
    assert image.is_file() and image.stat().st_size > 1000
    payload = json.loads(sidecar.read_text("utf-8"))
    assert payload["schema"] == "mmflow-figure-sidecar/v2"
    assert payload["question_id"] == "Q1"
    assert payload["backend"] == "python"
    assert payload["image_sha256"]


def test_generate_all_batch_report(module_inputs, tmp_path):
    plan = {
        "schema": "mmflow-figure-plan-input/v1",
        "items": [
            {"role": "heatmap", "data": module_inputs[heatmap]},
            {"role": "radar", "data": module_inputs[radar]},
            {"role": "not_a_role", "data": module_inputs[radar]},
        ],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "batch"
    code = generate_all.main(["--plan", str(plan_path), "--out-dir", str(out_dir)])
    assert code == 1  # one planned error must not abort the batch
    report = json.loads((out_dir / "generation_report.json").read_text("utf-8"))
    assert report["ok"] == 2 and report["errors"] == 1
    assert (out_dir / "heatmap.png").is_file()
    assert (out_dir / "radar.sidecar.json").is_file()


def test_radar_rejects_mismatched_series(base_input, tmp_path):
    with pytest.raises(ValueError, match="one score per indicator"):
        radar.generate(
            {
                **base_input,
                "indicators": ["a", "b", "c"],
                "series": {"A": [0.1, 0.2]},
            },
            tmp_path,
        )


def test_convergence_requires_positive_values(base_input, tmp_path):
    with pytest.raises(ValueError, match="positive"):
        convergence.generate(
            {**base_input, "h": [0.1, 0.05], "error": [1.0, -2.0]}, tmp_path
        )


def test_pareto_separates_front_and_dominated(base_input, tmp_path):
    result = pareto.generate(
        {**base_input, "points": [[0, 10], [1, 1], [2, 0], [1.5, 5]]}, tmp_path
    )
    assert Path(result["image_path"]).stat().st_size > 1000


def test_scatter_fit_baseline_must_match_length(base_input, tmp_path):
    with pytest.raises(ValueError, match="baseline_y"):
        scatter_fit.generate(
            {**base_input, "x": [1, 2], "y": [1, 2], "baseline_y": [1]}, tmp_path
        )
