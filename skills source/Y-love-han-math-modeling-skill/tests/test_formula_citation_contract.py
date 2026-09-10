"""M04/M05: formula-v1 per-type contract and citation depth contract."""

from __future__ import annotations

import pytest

from helpers import build_through, reg

from scripts.mmflow_core.errors import ConfigError


def _formula(**overrides) -> dict:
    payload = {
        "formula_id": "formula_x",
        "formula_type": "theoretical",
        "expression": r"E = m c^2",
        "symbols": [{"name": "E", "unit": "J", "meaning": "能量"}, {"name": "m"}],
        "premises": ["光速不变"],
        "derivation": ["由狭义相对论导出"],
        "boundary_cases": ["m=0 时光子"],
        "theorem_conditions": ["惯性系"],
        "citations": [],
        "dependencies": [],
        "display_values": ["1"],
        "status": "VALID",
    }
    payload.update(overrides)
    return payload


def test_theoretical_formula_requires_conditions_and_derivation(tmp_path):
    runtime, _ = build_through(tmp_path, "P2")
    with pytest.raises(ConfigError):
        reg(
            runtime,
            "formula",
            _formula(theorem_conditions=None),
            stage="P2",
        )
    with pytest.raises(ConfigError):
        reg(runtime, "formula", _formula(formula_type="bogus"), stage="P2")


def test_empirical_formula_requires_data_basis(tmp_path):
    runtime, _ = build_through(tmp_path, "P2")
    with pytest.raises(ConfigError):
        reg(runtime, "formula", _formula(formula_type="empirical"), stage="P2")
    record = reg(
        runtime,
        "formula",
        _formula(
            formula_type="empirical",
            data_basis={"artifact_id": "art_problem"},
            fitting_evidence=["R2=0.99"],
        ),
        stage="P2",
    )
    assert record["payload"]["formula_type"] == "empirical"


def test_optimization_formula_requires_objective_and_constraints(tmp_path):
    runtime, _ = build_through(tmp_path, "P2")
    with pytest.raises(ConfigError):
        reg(
            runtime,
            "formula",
            _formula(formula_type="optimization", objective="min cost"),
            stage="P2",
        )


def test_statistical_formula_requires_assumptions_and_uncertainty(tmp_path):
    runtime, _ = build_through(tmp_path, "P2")
    with pytest.raises(ConfigError):
        reg(runtime, "formula", _formula(formula_type="statistical"), stage="P2")


def test_symbols_must_be_named(tmp_path):
    runtime, _ = build_through(tmp_path, "P2")
    with pytest.raises(ConfigError):
        reg(runtime, "formula", _formula(symbols=[{"unit": "m"}]), stage="P2")


def _citation(**overrides) -> dict:
    payload = {
        "citation_id": "cite_x",
        "title": "文献标题",
        "authors": ["作者甲", "作者乙"],
        "year": "2024",
        "source_url": "https://example.org/paper",
        "access_level": "public",
        "verified_at": "2026-08-01T00:00:00+00:00",
        "verification_status": "verified",
        "source_role": "academic",
        "version": "v1",
        "metadata_verification": {"method": "doi_check", "checks": ["doi_resolves"]},
        "supports_claims": [],
        "status": "VALID",
    }
    payload.update(overrides)
    return payload


def test_citation_requires_authors_and_year(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    with pytest.raises(ConfigError):
        reg(runtime, "citation", _citation(authors=[]))
    with pytest.raises(ConfigError):
        reg(runtime, "citation", _citation(year=None))


def test_citation_enums_are_strict(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    with pytest.raises(ConfigError):
        reg(runtime, "citation", _citation(access_level="open_archive"))
    with pytest.raises(ConfigError):
        reg(runtime, "citation", _citation(verification_status="trusted"))
    with pytest.raises(ConfigError):
        reg(runtime, "citation", _citation(source_role="blog"))
    with pytest.raises(ConfigError):
        reg(runtime, "citation", _citation(metadata_verification="verified!"))


def test_citation_full_contract_passes(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    record = reg(runtime, "citation", _citation())
    assert record["payload"]["verification_status"] == "verified"


def test_retracted_citation_is_rejected_at_p3(tmp_path):
    from helpers import advance, begin, gate, p3_evidence
    from scripts.mmflow_core.audit import semantic_stage_check

    runtime, _ = build_through(tmp_path, "P2")
    reg(runtime, "citation", _citation(citation_id="cite_retracted", verification_status="retracted"))
    report = gate(runtime, "P2")
    assert report["status"] == "PASS"
    advance(runtime, "P2")
    begin(runtime, "P3")
    p3_evidence(runtime, literature_ids=["cite_retracted"])
    result = semantic_stage_check(runtime, "P3")
    assert result.status == "FAIL"
    assert "metadata-verified" in result.reason
