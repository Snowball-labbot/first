"""C14: invalidate propagates the full descendant set and rolls back."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import build_through

from scripts.mmflow import build_parser


def _invoke_cli(args: list[str]):
    parser = build_parser()
    namespace = parser.parse_args(args)
    from scripts.mmflow import dispatch

    payload, code = dispatch(namespace)
    return payload, int(code)


def test_invalidate_rolls_back_and_stales_descendants(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    project_root = runtime.project_root
    payload, code = _invoke_cli(
        [
            "invalidate",
            "--project",
            str(project_root),
            "--id",
            "res_main",
            "--reason",
            "根因废弃",
        ]
    )
    assert code == 0
    assert "res_main" in payload["affected"]
    assert "ev_results" in payload["affected"]
    assert payload["rollback_stage"] == "P5"
    assert payload["rerun_scope"] == ["P5", "P6", "P7", "P8", "P9", "P10", "P11"]
    # Statuses: root INVALID, dependent evidence STALE.
    assert runtime.registry.latest("result", "res_main")["payload"]["status"] == "INVALID"
    assert runtime.registry.latest("evidence", "ev_results")["payload"]["status"] == "STALE"
    state = runtime.workflow.state()
    assert state["active_stage"] == "P5"
    assert state["stage_epochs"]["P5"] == 2


def test_invalidate_unknown_entity_fails_closed(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    project_root = runtime.project_root
    with pytest.raises(Exception) as error:
        _invoke_cli(
            [
                "invalidate",
                "--project",
                str(project_root),
                "--id",
                "no_such_entity",
                "--reason",
                "x",
            ]
        )
    assert "unknown" in str(error.value) or "entity" in str(error.value)


def test_revise_entity_command_is_gone():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["revise-entity", "--project", ".", "--kind", "x"])
