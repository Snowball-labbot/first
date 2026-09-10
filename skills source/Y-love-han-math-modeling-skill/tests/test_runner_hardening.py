"""M09/M10/M11: runner secrets, statistical comparison and reproduction
conditions."""

from __future__ import annotations

import pytest
from pathlib import Path

from helpers import build_through, run_production, write_file

from scripts.mmflow_core.errors import ConfigError
from scripts.mmflow_core.runner import ExecutionRunner


def test_environment_secrets_are_rejected(tmp_path):
    from helpers import reg

    runtime, _ = build_through(tmp_path, "P5")
    leak_path = write_file(
        runtime.project_root,
        "code/leak.py",
        "import os\nprint('ok')\n",
    )
    reg(
        runtime,
        "artifact",
        {
            "artifact_id": "art_leak",
            "artifact_class": "external",
            "artifact_type": "source_code",
            "status": "VALID",
            "relative_path": "code/leak.py",
            "sha256": __import__("hashlib").sha256(
                (runtime.project_root / "code/leak.py").read_bytes()
            ).hexdigest(),
            "size_bytes": leak_path.stat().st_size,
            "inputs": [],
        },
        stage="P5",
    )
    with pytest.raises(ConfigError) as error:
        run_production(
            runtime,
            "P5",
            "q1",
            "leak",
            code_files=["code/leak.py"],
            input_files=[],
            config_files=[],
            source_artifact_ids=["art_leak"],
            expected_outputs=["out.txt"],
            comparison_policies={"out.txt": {"mode": "sha256"}},
            environment={"MY_API_TOKEN": "secret"},
            program="code/leak.py",
        )
    assert "secrets" in str(error.value) or "token" in str(error.value).lower()


def test_runner_shortens_deep_attempt_working_directory_without_moving_evidence(tmp_path):
    """Windows CreateProcess rejects a cwd at the legacy MAX_PATH boundary.

    The immutable attempt record may remain deeply nested for lineage, but
    the process itself must execute from a short external runtime directory.
    """
    runtime, _ = build_through(tmp_path, "P5")
    script = write_file(
        runtime.project_root,
        "code/deep_path_probe.py",
        "import os\n"
        "from pathlib import Path\n"
        "Path(os.environ['MMFLOW_OUTPUT_DIR']).joinpath('probe.txt').write_text('ok', encoding='utf-8')\n",
    )
    from helpers import reg

    reg(
        runtime,
        "artifact",
        {
            "artifact_id": "art_deep_path_probe",
            "artifact_class": "external",
            "artifact_type": "source_code",
            "status": "VALID",
            "relative_path": "code/deep_path_probe.py",
            "sha256": __import__("hashlib").sha256(script.read_bytes()).hexdigest(),
            "size_bytes": script.stat().st_size,
            "inputs": [],
        },
        stage="P5",
    )
    result = run_production(
        runtime,
        "P5",
        "q1",
        "deep_path_probe",
        code_files=["code/deep_path_probe.py"],
        input_files=[],
        config_files=[],
        source_artifact_ids=["art_deep_path_probe"],
        expected_outputs=["probe.txt"],
        comparison_policies={"probe.txt": {"mode": "sha256"}},
        program="code/deep_path_probe.py",
    )

    payload = result.execution["payload"]
    assert payload["status"] == "VALID"
    assert payload["working_directory"].startswith("runs/")
    assert len(result.artifacts) == 1


def test_runner_cleans_external_workspace_when_attestation_fails(tmp_path, monkeypatch):
    """A failed Registry START must not leak the ephemeral execution cwd."""
    from helpers import reg

    runtime, _ = build_through(tmp_path, "P5")
    script = write_file(
        runtime.project_root,
        "code/attestation_failure.py",
        "import os\n"
        "from pathlib import Path\n"
        "Path(os.environ['MMFLOW_OUTPUT_DIR']).joinpath('out.txt').write_text('ok', encoding='utf-8')\n",
    )
    reg(
        runtime,
        "artifact",
        {
            "artifact_id": "art_attestation_failure",
            "artifact_class": "external",
            "artifact_type": "source_code",
            "status": "VALID",
            "relative_path": "code/attestation_failure.py",
            "sha256": __import__("hashlib").sha256(script.read_bytes()).hexdigest(),
            "size_bytes": script.stat().st_size,
            "inputs": [],
        },
        stage="P5",
    )

    original = ExecutionRunner._short_execution_workspace
    captured: dict[str, Path] = {}

    def capture(cls, logical_sandbox):
        workspace, process_sandbox = original(logical_sandbox)
        captured["workspace"] = workspace
        return workspace, process_sandbox

    monkeypatch.setattr(
        ExecutionRunner,
        "_short_execution_workspace",
        classmethod(capture),
    )

    def fail_start(*_args, **_kwargs):
        raise ConfigError("synthetic attestation failure")

    monkeypatch.setattr(runtime.registry, "start_execution", fail_start)
    with pytest.raises(ConfigError, match="synthetic attestation failure"):
        run_production(
            runtime,
            "P5",
            "q1",
            "attestation_failure",
            code_files=["code/attestation_failure.py"],
            input_files=[],
            config_files=[],
            source_artifact_ids=["art_attestation_failure"],
            expected_outputs=["out.txt"],
            comparison_policies={"out.txt": {"mode": "sha256"}},
            program="code/attestation_failure.py",
        )

    assert "workspace" in captured
    assert not captured["workspace"].exists()


def test_runner_cleans_workspace_when_safe_environment_setup_fails(tmp_path, monkeypatch):
    """A failure after workspace creation but before START leaves no cwd copy."""
    from helpers import reg

    runtime, _ = build_through(tmp_path, "P5")
    script = write_file(
        runtime.project_root,
        "code/environment_failure.py",
        "from pathlib import Path\nPath('unused.txt').write_text('unused', encoding='utf-8')\n",
    )
    reg(
        runtime,
        "artifact",
        {
            "artifact_id": "art_environment_failure",
            "artifact_class": "external",
            "artifact_type": "source_code",
            "status": "VALID",
            "relative_path": "code/environment_failure.py",
            "sha256": __import__("hashlib").sha256(script.read_bytes()).hexdigest(),
            "size_bytes": script.stat().st_size,
            "inputs": [],
        },
        stage="P5",
    )
    original_workspace = ExecutionRunner._short_execution_workspace
    captured: dict[str, Path] = {}

    def capture(cls, logical_sandbox):
        workspace, process_sandbox = original_workspace(logical_sandbox)
        captured["workspace"] = workspace
        return workspace, process_sandbox

    monkeypatch.setattr(ExecutionRunner, "_short_execution_workspace", classmethod(capture))

    def fail_environment(*_args, **_kwargs):
        raise ConfigError("synthetic environment setup failure")

    monkeypatch.setattr(ExecutionRunner, "_safe_environment", staticmethod(fail_environment))
    with pytest.raises(ConfigError, match="synthetic environment setup failure"):
        run_production(
            runtime,
            "P5",
            "q1",
            "environment_failure",
            code_files=["code/environment_failure.py"],
            input_files=[],
            config_files=[],
            source_artifact_ids=["art_environment_failure"],
            expected_outputs=["out.txt"],
            comparison_policies={"out.txt": {"mode": "sha256"}},
            program="code/environment_failure.py",
        )

    assert "workspace" in captured
    assert not captured["workspace"].exists()


def test_runner_cleans_workspace_when_post_process_snapshot_fails(tmp_path, monkeypatch):
    """Unexpected failures after START must still remove the short workspace."""
    from helpers import reg

    runtime, _ = build_through(tmp_path, "P5")
    script = write_file(
        runtime.project_root,
        "code/post_snapshot_failure.py",
        "import os\n"
        "from pathlib import Path\n"
        "Path(os.environ['MMFLOW_OUTPUT_DIR']).joinpath('out.txt').write_text('ok', encoding='utf-8')\n",
    )
    reg(
        runtime,
        "artifact",
        {
            "artifact_id": "art_post_snapshot_failure",
            "artifact_class": "external",
            "artifact_type": "source_code",
            "status": "VALID",
            "relative_path": "code/post_snapshot_failure.py",
            "sha256": __import__("hashlib").sha256(script.read_bytes()).hexdigest(),
            "size_bytes": script.stat().st_size,
            "inputs": [],
        },
        stage="P5",
    )

    original_workspace = ExecutionRunner._short_execution_workspace
    captured: dict[str, Path] = {}

    def capture(cls, logical_sandbox):
        workspace, process_sandbox = original_workspace(logical_sandbox)
        captured["workspace"] = workspace
        return workspace, process_sandbox

    monkeypatch.setattr(
        ExecutionRunner,
        "_short_execution_workspace",
        classmethod(capture),
    )

    original_snapshot = ExecutionRunner._snapshot_files
    calls = {"count": 0}

    def fail_after_process(root):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("synthetic post-process snapshot failure")
        return original_snapshot(root)

    monkeypatch.setattr(
        ExecutionRunner,
        "_snapshot_files",
        staticmethod(fail_after_process),
    )
    with pytest.raises(RuntimeError, match="synthetic post-process snapshot failure"):
        run_production(
            runtime,
            "P5",
            "q1",
            "post_snapshot_failure",
            code_files=["code/post_snapshot_failure.py"],
            input_files=[],
            config_files=[],
            source_artifact_ids=["art_post_snapshot_failure"],
            expected_outputs=["out.txt"],
            comparison_policies={"out.txt": {"mode": "sha256"}},
            program="code/post_snapshot_failure.py",
        )

    assert "workspace" in captured
    assert not captured["workspace"].exists()


def test_statistical_json_comparison():
    left = {"values": [1.0, 2.0, 3.0, 4.0]}
    right = {"values": [1.0, 2.0, 3.0, 4.0]}
    equal, detail = ExecutionRunner._compare_statistical_json(
        left,
        right,
        {
            "statistic": "mean",
            "absolute_tolerance": 0.0,
            "relative_tolerance": 0.0,
            "n_seeds": 5,
            "min_sample_size": 4,
        },
    )
    assert equal is True
    assert detail["n_left"] == 4
    drifted = {"values": [1.0, 2.0, 3.0, 4.0]}
    equal, _ = ExecutionRunner._compare_statistical_json(
        left,
        drifted,
        {
            "statistic": "mean",
            "absolute_tolerance": 0.01,
            "relative_tolerance": 0.0,
        },
    )
    assert equal is True
    equal, _ = ExecutionRunner._compare_statistical_json(
        left,
        {"values": [10.0, 20.0, 30.0, 40.0]},
        {
            "statistic": "mean",
            "absolute_tolerance": 0.01,
            "relative_tolerance": 0.0,
        },
    )
    assert equal is False


def test_statistical_policy_frozen_contract(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    from scripts.mmflow_core.runner import ExecutionRequest, ExecutionRunner as ER

    bad = ExecutionRequest(
        stage="P5",
        question="q1",
        role="r",
        artifact_class="production",
        command=["python", "x.py"],
        expected_outputs=["out.json"],
        comparison_policies={
            "out.json": {"mode": "statistical_json", "statistic": "bogus"}
        },
    )
    with pytest.raises(ConfigError):
        ER._comparison_contract(bad)

    good = ExecutionRequest(
        stage="P5",
        question="q1",
        role="r",
        artifact_class="production",
        command=["python", "x.py"],
        expected_outputs=["out.json"],
        comparison_policies={
            "out.json": {
                "mode": "statistical_json",
                "statistic": "mean",
                "absolute_tolerance": 0.1,
                "relative_tolerance": 0.1,
                "n_seeds": 5,
                "min_sample_size": 10,
            }
        },
    )
    outputs, policies = ER._comparison_contract(good)
    assert outputs == ["out.json"]
    assert policies["out.json"]["mode"] == "statistical_json"


def test_reproduction_reuses_original_conditions(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    execution_id, _artifact, _result = None, None, None
    for record in runtime.registry.iter_latest("execution"):
        if record["payload"].get("role") == "model_main":
            execution_id = record["entity_id"]
            break
    assert execution_id is not None
    runner = ExecutionRunner(
        runtime.project_root, runtime.ledger, runtime.registry, runtime.run_id
    )
    reproduced = runner.reproduce(execution_id)
    payload = reproduced.execution["payload"]
    original = runtime.registry.latest("execution", execution_id)["payload"]
    assert payload["timeout_seconds"] == original["timeout_seconds"]
    assert payload["question"] == original["question"]
    assert payload["source_snapshots"] == original["source_snapshots"]

    def non_derived(environment: dict) -> dict:
        return {
            key: value
            for key, value in environment.items()
            if not key.startswith("MMFLOW_")
            and key
            not in {
                "PYTHONUTF8",
                "PYTHONHASHSEED",
                "PYTHONDONTWRITEBYTECODE",
                "PYTHONPYCACHEPREFIX",
                "TEMP",
                "TMP",
                "TMPDIR",
                "MYPY_CACHE_DIR",
                "RUFF_CACHE_DIR",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
                "PYTEST_ADDOPTS",
            }
        }

    # Reproduction reuses user-controlled conditions but receives fresh
    # per-attempt cache/temp roots so bytecode and tool caches cannot pollute
    # the project or collide with the original attempt.
    assert non_derived(payload["environment"]) == non_derived(original["environment"])
    for key in (
        "PYTHONPYCACHEPREFIX",
        "TEMP",
        "TMP",
        "TMPDIR",
        "MYPY_CACHE_DIR",
        "RUFF_CACHE_DIR",
    ):
        assert payload["environment"][key] != original["environment"][key]
        assert str(runtime.project_root) in payload["environment"][key]
        assert "runs" in Path(payload["environment"][key]).parts
    report = runner.compare_reproduction(execution_id, reproduced)
    assert report["outcome"] == "PASS"
    assert report["conditions"] == {}
