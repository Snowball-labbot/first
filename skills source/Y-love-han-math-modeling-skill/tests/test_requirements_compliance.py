"""C09/C10: structured requirements and the rule-driven compliance engine."""

from __future__ import annotations

import pytest

from helpers import begin, build_through, gate, make_runtime, p0_evidence, reg, write_file

from scripts.mmflow_core.compliance import (
    evaluate_requirements,
    validate_requirement,
    validate_requirements,
)
from scripts.mmflow_core.errors import IntegrityError


def _requirement(**overrides) -> dict:
    base = {
        "requirement_id": "submission.pdf_required",
        "kind": "boolean",
        "value": True,
        "scope": "paper",
        "severity": "HARD",
        "source_citation_id": "cite_rule",
        "snapshot_artifact_id": "art_rule",
        "source_locator": {"type": "page_clause", "page": 2, "clause": "4.1"},
        "verification_method": "artifact_presence",
    }
    base.update(overrides)
    return base


def test_requirement_schema_validation():
    assert validate_requirement(_requirement()) == []
    assert validate_requirement(_requirement(kind="boolean", value=1)) != []
    assert validate_requirement(_requirement(kind="number", value=True)) != []
    assert validate_requirement(_requirement(kind="pattern", value="[")) != []
    assert validate_requirement(_requirement(severity="MAYBE")) != []
    assert validate_requirement(_requirement(source_locator={"type": "page"})) != []
    assert validate_requirement(_requirement(verification_method="magic")) != []
    assert validate_requirement("nope") != []


def test_requirement_id_uniqueness():
    errors = validate_requirements(
        [_requirement(), _requirement(requirement_id="submission.pdf_required")]
    )
    assert any("duplicate" in error for error in errors)
    assert validate_requirements([]) == []


def test_p0_gate_rejects_malformed_requirements(tmp_path):
    runtime = make_runtime(tmp_path)
    begin(runtime, "P0")
    p0_evidence(runtime, requirements=[{"anonymous": True}])
    report = gate(runtime, "P0")
    assert report["status"] == "FAIL"
    semantic = {
        check["rule_id"]: check
        for check in report["checks"]
        if check["rule_id"] == "SEMANTIC-P0"
    }
    assert semantic["SEMANTIC-P0"]["reason"].startswith("competition rule requirements")


def test_p0_gate_accepts_structured_requirements(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    report = gate(runtime, "P0")
    assert report["status"] == "PASS"


def _register_pdf_artifact(runtime) -> None:
    path = write_file(
        runtime.project_root,
        "deliverables/paper.pdf",
        b"%PDF-1.4\n1 0 obj<</Type /Page /Parent 2 0 R>>endobj\n"
        b"2 0 obj<</Type /Pages /Kids[1 0 R]/Count 1>>endobj\n"
        b"trailer<</Root 2 0 R>>\n%%EOF",
    )
    # Use the P5 production execution as the producer.
    execution_id = None
    for record in runtime.registry.iter_latest("execution"):
        if record["payload"].get("role") == "model_main":
            execution_id = record["entity_id"]
            break
    assert execution_id is not None
    reg(
        runtime,
        "artifact",
        {
            "artifact_id": "art_pdf",
            "artifact_class": "production",
            "artifact_type": "paper_pdf",
            "status": "VALID",
            "execution_id": execution_id,
            "relative_path": "deliverables/paper.pdf",
            "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
            "media_type": "application/pdf",
            "inputs": [],
        },
        stage="P11",
    )


def test_compliance_engine_pdf_required(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    checks = evaluate_requirements(runtime, [_requirement()])
    assert checks[0]["status"] == "FAIL"  # no production PDF yet
    _register_pdf_artifact(runtime)
    checks = evaluate_requirements(runtime, [_requirement()])
    assert checks[0]["status"] == "PASS"


def test_compliance_engine_pdf_optional(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    checks = evaluate_requirements(
        runtime, [_requirement(value=False)]
    )
    assert checks[0]["status"] == "PASS"  # no PDF and none required


def test_compliance_engine_page_limits_from_real_pdf(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    _register_pdf_artifact(runtime)
    max_check = evaluate_requirements(
        runtime,
        [
            _requirement(
                requirement_id="submission.page_max",
                kind="number",
                value=10,
                verification_method="pdf_page_count",
            )
        ],
    )
    assert max_check[0]["status"] == "PASS"  # 1 page <= 10
    min_check = evaluate_requirements(
        runtime,
        [
            _requirement(
                requirement_id="submission.page_min",
                kind="number",
                value=5,
                verification_method="pdf_page_count",
            )
        ],
    )
    assert min_check[0]["status"] == "FAIL"  # 1 page < 5


def test_compliance_engine_filename_pattern(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    _register_pdf_artifact(runtime)
    checks = evaluate_requirements(
        runtime,
        [
            _requirement(
                requirement_id="submission.pdf_filename",
                kind="pattern",
                value=r"paper\.pdf",
                verification_method="filename_pattern",
            )
        ],
    )
    assert checks[0]["status"] == "PASS"
    checks = evaluate_requirements(
        runtime,
        [
            _requirement(
                requirement_id="submission.pdf_filename",
                kind="pattern",
                value=r"A2026\d+\.pdf",
                verification_method="filename_pattern",
            )
        ],
    )
    assert checks[0]["status"] == "FAIL"


def test_compliance_engine_hard_unverifiable_fails(tmp_path):
    runtime, _ = build_through(tmp_path, "P5")
    checks = evaluate_requirements(
        runtime,
        [
            _requirement(
                requirement_id="submission.mystery",
                verification_method="manual_check",
            )
        ],
    )
    assert checks[0]["status"] == "FAIL"
