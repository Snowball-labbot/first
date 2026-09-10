from __future__ import annotations

import pytest

from helpers import build_through, reg
from scripts.mmflow_core.errors import ConfigError, IntegrityError, UntrustedArtifactError
from test_figure_sidecar import _plot_execution


def _production_figure_payload(outputs: dict, *, generator: str = "art_plot_v2") -> dict:
    return {
        "figure_id": "fig_contract",
        "artifact_id": outputs["figure.png"]["artifact_id"],
        "sidecar_artifact_id": outputs["figure.sidecar.json"]["artifact_id"],
        "source_results": ["res_main"],
        "caption_claims": [],
        "status": "VALID",
        "question_id": "q1",
        "role": "model_result",
        "necessity": "required",
        "backend": "python",
        "generator_artifact_id": generator,
        "input_artifact_ids": ["art_problem"],
        "units": {"x": "unit", "y": "unit"},
        "uncertainty_description": "95% bootstrap interval",
        "information_gain": "shows main result against baseline",
        "paper_locator": "section:results;figure:1",
        "rendering_audit_id": "audit_render",
    }


def test_production_figure_requires_question_and_rendering_contract(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    _execution_id, outputs = _plot_execution(runtime, tag="_missing", schema="mmflow-figure-sidecar/v2")
    payload = _production_figure_payload(outputs, generator="art_plot_missing")
    payload.pop("question_id")
    with pytest.raises(ConfigError, match="question_id"):
        reg(runtime, "figure", payload, stage="P5")


def test_v2_production_figure_registers_when_every_binding_is_attested(tmp_path):
    """The v2 gate must have a usable all-production happy path.

    This is deliberately not a hand-written Registry record: image and
    sidecar come from one controlled production execution, and the generator
    and input artifacts are the registered external sources used by it.
    """
    runtime, _ = build_through(tmp_path, "P5")
    execution_id, outputs = _plot_execution(
        runtime,
        tag="_positive",
        schema="mmflow-figure-sidecar/v2",
        generator_artifact_id="art_plot_positive",
    )

    registered = reg(
        runtime,
        "figure",
        _production_figure_payload(outputs, generator="art_plot_positive"),
        stage="P5",
    )

    assert registered["payload"]["figure_id"] == "fig_contract"
    assert registered["payload"]["artifact_id"] == outputs["figure.png"]["artifact_id"]
    assert registered["payload"]["sidecar_artifact_id"] == outputs["figure.sidecar.json"]["artifact_id"]
    assert execution_id == outputs["figure.png"]["execution_id"]


def test_demo_source_cannot_become_production_figure(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    _execution_id, outputs = _plot_execution(
        runtime,
        tag="_v2",
        schema="mmflow-figure-sidecar/v2",
        generator_artifact_id="demo_generator",
    )
    demo_path = runtime.project_root / "code" / "demo_generator.py"
    demo_path.write_text("# demo only\n", encoding="utf-8")
    reg(
        runtime,
        "artifact",
        {
            "artifact_id": "demo_generator",
            "artifact_class": "demo",
            "artifact_type": "source_code",
            "status": "VALID",
            "relative_path": "code/demo_generator.py",
            "sha256": __import__("hashlib").sha256(demo_path.read_bytes()).hexdigest(),
            "size_bytes": demo_path.stat().st_size,
            "inputs": [],
        },
        stage="P5",
    )
    with pytest.raises(UntrustedArtifactError, match="generator"):
        reg(
            runtime,
            "figure",
            _production_figure_payload(outputs, generator="demo_generator"),
            stage="P5",
        )


def test_v2_production_figure_rejects_result_from_another_question_at_registry_boundary(tmp_path):
    """A Figure's Result evidence must be in the same question scope.

    This deliberately omits the optional coverage-plan gate: the Registry
    itself must reject a cross-question binding so callers cannot bypass the
    question-aware planner.
    """
    runtime, _ = build_through(tmp_path, "P5")
    main_result = runtime.registry.latest("result", "res_main")["payload"]
    other_result = dict(main_result)
    other_result.update({"result_id": "res_other_question", "question_id": "q2"})
    reg(runtime, "result", other_result, stage="P5")
    _execution_id, outputs = _plot_execution(
        runtime,
        tag="_cross_scope",
        schema="mmflow-figure-sidecar/v2",
        generator_artifact_id="art_plot_cross_scope",
        source_result_id="res_other_question",
        question_id="q1",
    )
    payload = _production_figure_payload(outputs, generator="art_plot_cross_scope")
    payload["source_results"] = ["res_other_question"]
    with pytest.raises(IntegrityError, match="question_id"):
        reg(runtime, "figure", payload, stage="P5")
