"""M02/M03: result_kind enum and the counterevidence downgrade rule."""

from __future__ import annotations

import pytest

from helpers import build_through, reg

from scripts.mmflow_core.errors import ConfigError, IntegrityError


def test_invalid_result_kind_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    result = runtime.registry.latest("result", "res_main")["payload"]
    with pytest.raises(ConfigError):
        reg(
            runtime,
            "result",
            {**result, "result_id": "res_bad_kind", "result_kind": "whatever"},
            stage="P5",
        )


def test_valid_result_kinds_accepted(tmp_path):
    from scripts.mmflow_core.registry import RESULT_KINDS

    assert {"scalar", "vector", "table", "category", "set"} == RESULT_KINDS


def test_confirmed_claim_with_counterevidence_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P6")
    with pytest.raises(IntegrityError):
        reg(
            runtime,
            "claim",
            {
                "claim_id": "claim_confirmed_with_counter",
                "claim_type": "inferential",
                "statement": "存在反证的确认主张",
                "supports": ["res_main"],
                "counterevidence": ["ev_counter"],
                "scope": "给定数据集",
                "strength": "confirmed",
                "status": "VALID",
            },
            stage="P6",
        )


def test_downgraded_claim_with_counterevidence_accepted(tmp_path):
    runtime, _ = build_through(tmp_path, "P6")
    record = reg(
        runtime,
        "claim",
        {
            "claim_id": "claim_downgraded",
            "claim_type": "inferential",
            "statement": "存在反证的探索性主张",
            "supports": ["res_main"],
            "counterevidence": ["ev_counter"],
            "scope": "给定数据集",
            "strength": "exploratory",
            "status": "VALID",
        },
        stage="P6",
    )
    assert record["payload"]["strength"] == "exploratory"
