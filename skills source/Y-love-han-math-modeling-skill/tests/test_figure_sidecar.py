"""C11: figure image + sidecar same-execution lock."""

from __future__ import annotations

import json

import pytest

from helpers import begin, build_through, reg, run_production, write_file

from scripts.mmflow_core.errors import IntegrityError, UntrustedArtifactError


def _plot_execution(
    runtime,
    *,
    tag: str = "",
    schema: str = "mmflow-figure-sidecar/v1",
    generator_artifact_id: str | None = None,
    source_result_id: str = "res_main",
    question_id: str = "q1",
) -> tuple[str, dict]:
    """Run a production plotting execution writing image + sidecar."""
    generator_id = generator_artifact_id or f"art_plot{tag}"
    write_file(
        runtime.project_root,
        "code/plot.py",
        (
            "import hashlib, json, os\n"
            "out = os.environ['MMFLOW_OUTPUT_DIR']\n"
            "png = b'\\x89PNG\\r\\n\\x1a\\n' + b'\\x00' * 64\n"
            "with open(os.path.join(out, 'figure.png'), 'wb') as f:\n"
            "    f.write(png)\n"
            "sidecar = {\n"
            f"    'schema': '{schema}',\n"
            "    'image_sha256': hashlib.sha256(png).hexdigest(),\n"
            f"    'source_result_ids': ['{source_result_id}'],\n"
            "    'model_id': 'model_main',\n"
            "    'execution_id': os.environ.get('MMFLOW_EXECUTION_ID'),\n"
            "    'axes': [],\n"
            "    'series': [],\n"
            "    'sample_size': 100,\n"
            f"    'question_id': '{question_id}',\n"
            "    'role': 'model_result',\n"
            "    'backend': 'python',\n"
            f"    'generator_artifact_id': '{generator_id}',\n"
            "    'input_artifact_ids': ['art_problem'],\n"
            "    'units': {'x': 'unit', 'y': 'unit'},\n"
            "    'uncertainty_description': '95% bootstrap interval',\n"
            "    'information_gain': 'shows main result against baseline',\n"
            "    'paper_locator': 'section:results;figure:1',\n"
            "    'rendering_audit_id': 'audit_render',\n"
            "}\n"
            "with open(os.path.join(out, 'figure.sidecar.json'), 'w', encoding='utf-8') as f:\n"
            "    json.dump(sidecar, f)\n"
        ),
    )
    artifact_id = f"art_plot{tag}"
    reg(
        runtime,
        "artifact",
        {
            "artifact_id": artifact_id,
            "artifact_class": "external",
            "artifact_type": "source_code",
            "status": "VALID",
            "relative_path": "code/plot.py",
            "sha256": __import__("hashlib").sha256(
                (runtime.project_root / "code/plot.py").read_bytes()
            ).hexdigest(),
            "size_bytes": (runtime.project_root / "code/plot.py").stat().st_size,
            "inputs": [],
        },
        stage="P5",
    )
    result = run_production(
        runtime,
        "P5",
        "q1",
        "plot",
        code_files=["code/plot.py"],
        input_files=[],
        config_files=[],
        source_artifact_ids=[artifact_id],
        expected_outputs=["figure.png", "figure.sidecar.json"],
        comparison_policies={
            "figure.png": {"mode": "sha256"},
            "figure.sidecar.json": {"mode": "sha256"},
        },
        program="code/plot.py",
    )
    execution_id = result.execution["payload"]["execution_id"]
    by_output = {
        item["payload"]["logical_output_path"]: item["payload"]
        for item in result.artifacts
    }
    return execution_id, by_output


def test_figure_sidecar_same_execution_lock_passes(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    execution_id, outputs = _plot_execution(runtime)
    reg(
        runtime,
        "figure",
        {
            "figure_id": "fig_main",
            "artifact_id": outputs["figure.png"]["artifact_id"],
            "sidecar_artifact_id": outputs["figure.sidecar.json"]["artifact_id"],
            "source_results": ["res_main"],
            "caption_claims": [],
            "status": "VALID",
        },
        stage="P5",
    )


def test_sidecar_wrong_image_hash_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    execution_id, outputs = _plot_execution(runtime)
    sidecar_path = runtime.project_root / outputs["figure.sidecar.json"]["relative_path"]
    sidecar = json.loads(sidecar_path.read_text("utf-8"))
    sidecar["execution_id"] = execution_id
    sidecar["image_sha256"] = "0" * 64
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(IntegrityError):
        reg(
            runtime,
            "figure",
            {
                "figure_id": "fig_bad_hash",
                "artifact_id": outputs["figure.png"]["artifact_id"],
                "sidecar_artifact_id": outputs["figure.sidecar.json"]["artifact_id"],
                "source_results": ["res_main"],
                "caption_claims": [],
                "status": "VALID",
            },
            stage="P5",
        )


def test_sidecar_wrong_result_set_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    execution_id, outputs = _plot_execution(runtime)
    sidecar_path = runtime.project_root / outputs["figure.sidecar.json"]["relative_path"]
    sidecar = json.loads(sidecar_path.read_text("utf-8"))
    sidecar["execution_id"] = execution_id
    sidecar["source_result_ids"] = ["res_other"]
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(IntegrityError):
        reg(
            runtime,
            "figure",
            {
                "figure_id": "fig_bad_results",
                "artifact_id": outputs["figure.png"]["artifact_id"],
                "sidecar_artifact_id": outputs["figure.sidecar.json"]["artifact_id"],
                "source_results": ["res_main"],
                "caption_claims": [],
                "status": "VALID",
            },
            stage="P5",
        )


def test_sidecar_wrong_schema_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    execution_id, outputs = _plot_execution(runtime)
    sidecar_path = runtime.project_root / outputs["figure.sidecar.json"]["relative_path"]
    sidecar = json.loads(sidecar_path.read_text("utf-8"))
    sidecar["execution_id"] = execution_id
    sidecar["schema"] = "other/v1"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(IntegrityError):
        reg(
            runtime,
            "figure",
            {
                "figure_id": "fig_bad_schema",
                "artifact_id": outputs["figure.png"]["artifact_id"],
                "sidecar_artifact_id": outputs["figure.sidecar.json"]["artifact_id"],
                "source_results": ["res_main"],
                "caption_claims": [],
                "status": "VALID",
            },
            stage="P5",
        )


def test_sidecar_from_different_execution_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    _execution_id, outputs = _plot_execution(runtime, tag="_a")
    # A second plot run produces a sidecar bound to a different execution.
    _other_id, other_outputs = _plot_execution(runtime, tag="_b")
    with pytest.raises(IntegrityError):
        reg(
            runtime,
            "figure",
            {
                "figure_id": "fig_foreign",
                "artifact_id": outputs["figure.png"]["artifact_id"],
                "sidecar_artifact_id": other_outputs["figure.sidecar.json"]["artifact_id"],
                "source_results": ["res_main"],
                "caption_claims": [],
                "status": "VALID",
            },
            stage="P5",
        )


def test_v2_sidecar_rejects_demo_generator_after_real_artifacts_exist(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    _execution_id, outputs = _plot_execution(
        runtime,
        tag="_v2",
        schema="mmflow-figure-sidecar/v2",
        generator_artifact_id="demo_generator",
    )
    demo_path = write_file(runtime.project_root, "code/demo_generator.py", "# demo only\n")
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
            {
                "figure_id": "fig_demo_generator",
                "artifact_id": outputs["figure.png"]["artifact_id"],
                "sidecar_artifact_id": outputs["figure.sidecar.json"]["artifact_id"],
                "source_results": ["res_main"],
                "caption_claims": [],
                "status": "VALID",
                "question_id": "q1",
                "role": "model_result",
                "necessity": "required",
                "backend": "python",
                "generator_artifact_id": "demo_generator",
                "input_artifact_ids": ["art_problem"],
                "units": {"x": "unit", "y": "unit"},
                "uncertainty_description": "95% bootstrap interval",
                "information_gain": "shows main result against baseline",
                "paper_locator": "section:results;figure:1",
                "rendering_audit_id": "audit_render",
            },
            stage="P5",
        )
