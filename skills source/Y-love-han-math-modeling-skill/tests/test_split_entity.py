"""M07: dataset splits are first-class immutable entities."""

from __future__ import annotations

import pytest

from helpers import begin, build_through, reg

from scripts.mmflow_core.errors import ConfigError, IntegrityError
from scripts.mmflow_core.lineage import LineageGraph


def _split_payload(**overrides) -> dict:
    payload = {
        "split_id": "split_test",
        "source_dataset_artifact_id": "art_problem",
        "split_kind": "time",
        "selectors": {"cutoff": "2025-01-01"},
        "indices_sha256": "a" * 64,
        "leakage_boundary": {"temporal": "no_future_lookahead"},
        "preprocessing_fit_scope": "train_only",
        "immutable_fingerprint": "b" * 64,
        "status": "VALID",
    }
    payload.update(overrides)
    return payload


def test_split_registration_requires_full_contract(tmp_path):
    runtime, _ = build_through(tmp_path, "P3")
    with pytest.raises(ConfigError):
        reg(runtime, "split", _split_payload(split_kind="whatever"), stage="P3")
    with pytest.raises(ConfigError):
        reg(runtime, "split", _split_payload(indices_sha256="not-a-hash"), stage="P3")
    with pytest.raises(ConfigError):
        reg(runtime, "split", _split_payload(preprocessing_fit_scope="test"), stage="P3")
    with pytest.raises(ConfigError):
        reg(runtime, "split", _split_payload(source_dataset_artifact_id=""), stage="P3")


def test_split_registration_passes(tmp_path):
    runtime, _ = build_through(tmp_path, "P3")
    record = reg(runtime, "split", _split_payload(), stage="P3")
    assert record["payload"]["split_kind"] == "time"


def test_execution_must_reference_registered_split(tmp_path):
    from helpers import run_production, write_file

    runtime, _ = build_through(tmp_path, "P4")
    write_file(
        runtime.project_root,
        "code/model2.py",
        "import json, os\n"
        "out = os.environ['MMFLOW_OUTPUT_DIR']\n"
        "with open(os.path.join(out, 'result.json'), 'w', encoding='utf-8') as f:\n"
        "    json.dump({'schema': 'mmflow-result-contract/v1', 'results': {}}, f)\n",
    )
    reg(
        runtime,
        "artifact",
        {
            "artifact_id": "art_model2",
            "artifact_class": "external",
            "artifact_type": "source_code",
            "status": "VALID",
            "relative_path": "code/model2.py",
            "sha256": __import__("hashlib").sha256(
                (runtime.project_root / "code/model2.py").read_bytes()
            ).hexdigest(),
            "size_bytes": (runtime.project_root / "code/model2.py").stat().st_size,
            "inputs": [],
        },
        stage="P4",
    )
    with pytest.raises(IntegrityError) as error:
        run_production(
            runtime,
            "P5",
            "q1",
            "model2",
            code_files=["code/model2.py"],
            input_files=[],
            config_files=[],
            source_artifact_ids=["art_model2"],
            expected_outputs=["result.json"],
            comparison_policies={"result.json": {"mode": "sha256"}},
            dataset_split_ids=["split_ghost"],
            program="code/model2.py",
        )
    assert "split" in str(error.value)


def test_split_enters_lineage_and_invalidation(tmp_path):
    runtime, _ = build_through(tmp_path, "P3")
    graph = LineageGraph(runtime.registry)
    assert "split_all" in graph.dependencies
    # Execution depends on the split (registered later at P5), and the split
    # itself depends on its source dataset artifact.
    assert "art_problem" in graph.dependencies["split_all"]
