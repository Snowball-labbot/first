"""C13: evidence content references must equal the explicit supports."""

from __future__ import annotations

import pytest

from helpers import begin, build_through, reg

from scripts.mmflow_core.errors import IntegrityError


def test_declared_support_missing_from_content_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P1")
    with pytest.raises(IntegrityError) as error:
        reg(
            runtime,
            "evidence",
            {
                "evidence_id": "ev_under",
                "evidence_type": "input_inventory",
                "status": "VALID",
                "content": {
                    "files": [{"artifact_id": "art_problem"}],
                    "critical_missing": False,
                },
                "supports": [],
            },
            stage="P1",
        )
    assert "dependency mismatch" in str(error.value)


def test_extra_support_not_in_content_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P1")
    with pytest.raises(IntegrityError) as error:
        reg(
            runtime,
            "evidence",
            {
                "evidence_id": "ev_over",
                "evidence_type": "input_inventory",
                "status": "VALID",
                "content": {
                    "files": [{"artifact_id": "art_problem"}],
                    "critical_missing": False,
                },
                "supports": ["art_problem", "art_rule"],
            },
            stage="P1",
        )
    assert "dependency mismatch" in str(error.value)


def test_exact_dependency_match_accepted(tmp_path):
    runtime, _ = build_through(tmp_path, "P1")
    record = reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_exact",
            "evidence_type": "input_inventory",
            "status": "VALID",
            "content": {
                "files": [{"artifact_id": "art_problem"}],
                "critical_missing": False,
            },
            "supports": ["art_problem"],
        },
        stage="P1",
    )
    assert record["payload"]["supports"] == ["art_problem"]


def test_nested_list_dependencies_extracted(tmp_path):
    from helpers import advance, gate, p2_evidence

    runtime, _ = build_through(tmp_path, "P1")
    report = gate(runtime, "P1")
    assert report["status"] == "PASS"
    advance(runtime, "P1")
    begin(runtime, "P2")
    p2_evidence(runtime)
    report = gate(runtime, "P2")
    assert report["status"] == "PASS"
    advance(runtime, "P2")
    begin(runtime, "P3")
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_nested",
            "evidence_type": "data_lineage",
            "status": "VALID",
            "content": {
                "sources": [{"artifact_id": "art_problem"}],
                "transforms": [{"artifact_id": "art_problem"}],
                "splits": [],
            },
            "supports": ["art_problem"],
        },
        stage="P3",
    )
