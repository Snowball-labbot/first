from __future__ import annotations

import json

from helpers import advance, begin, build_through, gate, p8_publication, reg
from test_figure_production_gate import _production_figure_payload
from test_figure_sidecar import _plot_execution


def _write_plan(runtime) -> None:
    (runtime.project_root / ".mmflow" / "figure-coverage-plan.json").write_text(
        json.dumps(
            {
                "schema": "mmflow-figure-coverage-plan/v1",
                "questions": ["q1"],
                "items": [
                    {
                        "question_id": "q1",
                        "role": "model_result",
                        "necessity": "required",
                        "source_requirements": {
                            "result_ids": ["res_main"],
                            "results_declared": True,
                            "production_only": True,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_p8_coverage_enriches_a_v2_registry_figure_from_its_image_artifact(tmp_path):
    runtime, _ = build_through(tmp_path, "P7")
    assert gate(runtime, "P7")["status"] == "PASS"
    advance(runtime, "P7")
    begin(runtime, "P8")
    p8_publication(runtime)
    _execution_id, outputs = _plot_execution(
        runtime,
        tag="_coverage",
        schema="mmflow-figure-sidecar/v2",
        generator_artifact_id="art_plot_coverage",
    )
    reg(
        runtime,
        "figure",
        _production_figure_payload(outputs, generator="art_plot_coverage"),
        stage="P8",
    )
    _write_plan(runtime)

    report = gate(runtime, "P8")

    assert report["status"] == "PASS", report


def test_p8_coverage_rejects_figure_bound_to_a_result_from_another_question(tmp_path):
    runtime, _ = build_through(tmp_path, "P7")
    assert gate(runtime, "P7")["status"] == "PASS"
    advance(runtime, "P7")
    begin(runtime, "P8")
    p8_publication(runtime)
    _execution_id, outputs = _plot_execution(
        runtime,
        tag="_cross_question",
        schema="mmflow-figure-sidecar/v2",
        generator_artifact_id="art_plot_cross_question",
    )
    reg(
        runtime,
        "figure",
        _production_figure_payload(outputs, generator="art_plot_cross_question"),
        stage="P8",
    )
    _write_plan(runtime)
    plan_path = runtime.project_root / ".mmflow" / "figure-coverage-plan.json"
    plan = json.loads(plan_path.read_text("utf-8"))
    plan["items"][0]["source_requirements"]["result_ids"] = ["res_other_question"]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    report = gate(runtime, "P8")

    assert report["status"] == "FAIL"
    assert "figure coverage" in " ".join(
        str(check.get("reason", "")) for check in report["checks"]
    ).lower()
