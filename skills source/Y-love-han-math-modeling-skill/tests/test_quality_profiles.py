from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from helpers import advance, begin, gate, make_runtime, p4_evidence, reg
from scripts.mmflow_core.quality import (
    SPECIAL_REVIEW_ROLES,
    _check_item,
    _validate_independent_provenance,
    _validate_special_assessment,
    quality_contract_check,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY_DIR = ROOT / "scripts" / "mmflow_core" / "policies"


def _common_content(*, applicability: str = "APPLICABLE") -> dict:
    return {
        "applicability": applicability,
        "not_applicable_reason": "",
        "not_applicable_detail": None,
        "alternative_evidence_ids": [],
        "source_entity_ids": [],
        "supported_claim_ids": [],
        "problem_ids": ["q1"],
        "method": "按问题合同、模型推导与独立复核记录进行检查",
        "checks": [{"check_id": "c1", "status": "PASS", "observation": "已完成"}],
        "limitations": ["结论仅适用于记录的题目、数据与假设范围"],
        "reviewer": "mathematics_numerics",
    }


def _fake_runtime(required_by_stage: dict[str, list[str]]):
    class Registry:
        def __init__(self, records):
            self.records = records

        def iter_latest(self, kind):
            return list(self.records) if kind == "evidence" else []

        def find_entity(self, entity_id):
            for record in self.records:
                if record["entity_id"] == entity_id:
                    return record
            raise KeyError(entity_id)

    records = []
    for stage, evidence_types in required_by_stage.items():
        for index, evidence_type in enumerate(evidence_types):
            content = _common_content()
            if evidence_type == "quality_profile_selection":
                content = {
                    "profile": "special-prize",
                    "selected_at": "2026-08-06T00:00:00+00:00",
                    "rationale": "题目复杂度和竞赛目标要求完整记录科学深度证据",
                    "frozen_with_analysis_plan": True,
                }
            elif evidence_type == "special_prize_quality_assessment":
                content = _common_content()
                content.update({
                    "level": "SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW",
                    "program_facts": ["所有结构化门禁通过"],
                    "experiment_supported": ["模型验证与复现"],
                    "professional_judgments": ["原创性需由独立评审判断"],
                    "cannot_guarantee": ["prize_outcome", "judge_preference"],
                })
            elif evidence_type == "paper_depth_review":
                content.update({"manuscript_sections": ["model", "validation", "limitations"]})
            elif evidence_type == "candidate_rejection_record":
                content.update({"candidates": [{"id": "m1", "decision": "REJECT", "quantitative_reason": "验证误差更高"}]})
            elif evidence_type == "formula_validity_record":
                content.update({"formulas": [{"formula_id": "f1", "checks": ["dimension", "domain", "boundary", "singularity"]}]})
            elif evidence_type == "theorem_application_record":
                content.update({"theorems": [{"name": "连续性定理", "conditions": ["条件A"], "application": "问题q1"}]})
            elif evidence_type == "innovation_ablation_record":
                content.update({"innovations": [{"id": "i1", "with": 1.0, "without": 1.2, "conclusion": "有效"}]})
            elif evidence_type == "counterintuitive_finding_record":
                content.update({"findings": [{"statement": "变量增加但目标下降", "explanation": "约束耦合"}]})
            elif evidence_type == "cross_problem_framework_record":
                content.update({"framework": "统一约束优化框架", "problem_links": ["q1"]})
            elif evidence_type == "mechanism_explanation_record":
                content.update({"explanations": [{"claim": "c1", "mathematical": "梯度项", "data": "相关结构", "domain": "业务机制"}]})
            elif evidence_type == "negative_result_record":
                content.update({"results": [{"attempt": "m2", "outcome": "未采用", "reason": "不稳定"}]})
            elif evidence_type == "independent_review_provenance":
                content = {
                    "reviewers": [],
                    "limitations": ["仅用于策略夹具，不代表真实独立执行"],
                }
            records.append({
                "entity_kind": "evidence",
                "entity_id": f"ev_{stage}_{index}_{evidence_type}",
                "created_stage": stage,
                "stage_epoch": 1,
                "created_ledger_sequence": index + 1,
                "payload": {
                    "status": "VALID",
                    "evidence_type": evidence_type,
                    "content": content,
                    "supports": [],
                },
            })

    class Runtime:
        contract = {"quality_profile": "special-prize"}
        registry = Registry(records)
        workflow = type("Workflow", (), {"snapshot": lambda self: {"stage_epochs": {f"P{i}": 1 for i in range(12)}}})()

    return Runtime()


def test_quality_profiles_policy_contains_special_prize_contract():
    policy = json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))
    assert policy["default"] == "adaptive"
    assert "special-prize" in policy["profiles"]
    special = policy["profiles"]["special-prize"]
    assert special["required_evidence_by_stage"]["P4"]
    assert "candidate_rejection_record" in special["core_evidence"]
    assert special["no_fixed_quotas"] is True


def test_depth_evidence_is_declared_in_all_policy_surfaces():
    schemas = json.loads((POLICY_DIR / "schemas-v1.json").read_text("utf-8"))
    evidence = json.loads((POLICY_DIR / "evidence-v1.json").read_text("utf-8"))
    manifest = json.loads((ROOT / "templates" / "template_manifest.json").read_text("utf-8"))
    names = {
        "theorem_application_record",
        "candidate_rejection_record",
        "formula_validity_record",
        "innovation_ablation_record",
        "counterintuitive_finding_record",
        "cross_problem_framework_record",
        "mechanism_explanation_record",
        "negative_result_record",
        "paper_depth_review",
        "special_prize_quality_assessment",
    }
    for name in names:
        assert name in schemas["evidence_contracts"]
        assert name in schemas["evidence_dependency_fields"]
        assert name in evidence["evidence_stage_matrix"]
    listed = {
        item
        for entry in manifest["templates"]
        for item in entry.get("evidence_types", [])
    }
    assert names <= listed


def test_special_prize_profile_fails_at_p4_without_depth_evidence(tmp_path):
    from scripts.mmflow_core.project import initialize_project

    runtime = initialize_project(
        tmp_path / "project", "CUMCM", "2026A", skill_root=ROOT, quality_profile="special-prize"
    )
    begin(runtime, "P0")
    from helpers import p0_evidence
    p0_evidence(runtime)
    report = gate(runtime, "P0")
    assert report["status"] == "PASS"
    from helpers import advance
    advance(runtime, "P0")
    for stage in ("P1", "P2", "P3"):
        begin(runtime, stage)
        from helpers import STAGE_BUILDERS
        STAGE_BUILDERS[stage](runtime)
        report = gate(runtime, stage)
        assert report["status"] == "PASS"
        advance(runtime, stage)
    begin(runtime, "P4")
    p4_evidence(runtime)
    result = quality_contract_check(runtime, "P4")
    assert result.status == "FAIL"
    assert "special-prize" in result.reason


def test_special_prize_allows_explicit_not_applicable_with_alternative():
    policy = json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))
    required = policy["profiles"]["special-prize"]["required_evidence_by_stage"]
    runtime = _fake_runtime(required)
    result = quality_contract_check(runtime, "P10")
    assert result.status == "PASS", result.reason


class _StrictRegistry:
    def __init__(self, records_by_kind: dict[str, list[dict]]):
        self.records_by_kind = records_by_kind

    def iter_latest(self, kind: str):
        return list(self.records_by_kind.get(kind, []))

    def find_entity(self, entity_id: str):
        for records in self.records_by_kind.values():
            for record in records:
                if record.get("entity_id") == entity_id:
                    return record
        raise KeyError(entity_id)

    def latest(self, kind: str, entity_id: str):
        for record in self.records_by_kind.get(kind, []):
            if record.get("entity_id") == entity_id:
                return record
        raise KeyError(entity_id)


def _strict_runtime_for_assessment():
    policy = json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))
    criteria = policy["profiles"]["special-prize"]["score_policy"]["criteria"]
    selected_types = [
        "quality_profile_selection",
        "formula_validity_record",
        "candidate_rejection_record",
        "innovation_ablation_record",
        "mechanism_explanation_record",
        "negative_result_record",
        "cross_problem_framework_record",
        "paper_depth_review",
        "independent_review_provenance",
    ]
    selected_stages = ["P4", "P4", "P4", "P6", "P6", "P6", "P6", "P8", "P10"]
    evidence = []
    for index, evidence_type in enumerate(selected_types):
        evidence.append(
            {
                "entity_kind": "evidence",
                "entity_id": f"ev_score_{index}",
                "created_stage": selected_stages[index],
                "stage_epoch": 1,
                "created_ledger_sequence": index + 1,
                "payload": {
                    "status": "VALID",
                    "evidence_type": evidence_type,
                    "content": {},
                    "supports": [],
                },
            }
        )
    runtime = SimpleNamespace(
        skill_root=ROOT,
        registry=_StrictRegistry({"evidence": evidence}),
        workflow=SimpleNamespace(
            snapshot=lambda: {
                "stage_epochs": {f"P{i}": 1 for i in range(12)},
                "stages": {
                    **{f"P{i}": "PASSED" for i in (4, 5, 6, 8)},
                    "P10": "ACTIVE",
                },
            }
        ),
    )
    content = _common_content()
    content.update(
        {
            "level": "SPECIAL_PRIZE_CANDIDATE_LIMITED_REVIEW",
            "program_facts": ["结构化门禁通过"],
            "experiment_supported": ["模型验证与复现"],
            "professional_judgments": ["原创性仍需评审判断"],
            "cannot_guarantee": ["prize_outcome", "judge_preference"],
            "criterion_results": [
                {
                    "id": criterion["id"],
                    "status": "PASS",
                    "earned": criterion["maximum"],
                    "evidence_ids": [f"ev_score_{index}"],
                }
                for index, criterion in enumerate(criteria)
            ],
            "total": 100.0,
        }
    )
    return runtime, content


def test_special_prize_score_is_recomputed_and_cannot_be_raised_by_earned_field():
    runtime, content = _strict_runtime_for_assessment()
    assert _validate_special_assessment(
        content,
        json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))["profiles"]["special-prize"],
        runtime,
    ) == []
    content["criterion_results"][0]["earned"] += 1.0
    errors = _validate_special_assessment(
        content,
        json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))["profiles"]["special-prize"],
        runtime,
    )
    assert any("policy-derived score" in error for error in errors)


def test_special_prize_declared_total_cannot_be_raised_without_evidence():
    runtime, content = _strict_runtime_for_assessment()
    content["total"] = 101.0
    errors = _validate_special_assessment(
        content,
        json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))["profiles"]["special-prize"],
        runtime,
    )
    assert any("policy-derived total" in error for error in errors)


def test_deep_insight_assessment_does_not_require_special_prize_score_policy():
    runtime, content = _strict_runtime_for_assessment()
    content.pop("criterion_results")
    content.pop("total")
    content["level"] = "QUALITY_REVIEW_READY"
    policy = json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))
    assert _validate_special_assessment(
        content, policy["profiles"]["deep-insight"], runtime
    ) == []


def test_quality_depth_contract_rejects_old_stage_epoch():
    runtime, content = _strict_runtime_for_assessment()
    record = {
        "entity_kind": "evidence",
        "entity_id": "ev_old_epoch",
        "created_stage": "P4",
        "stage_epoch": 1,
        "created_ledger_sequence": 1,
        "payload": {
            "status": "VALID",
            "evidence_type": "candidate_rejection_record",
            "content": content,
            "supports": [],
        },
    }
    runtime.workflow.snapshot = lambda: {
        "stage_epochs": {**{f"P{i}": 1 for i in range(12)}, "P4": 2},
        "stages": {
            **{f"P{i}": "PASSED" for i in (4, 5, 6, 8)},
            "P10": "ACTIVE",
        },
    }
    errors = _check_item(
        {"candidate_rejection_record": [record]},
        "candidate_rejection_record",
        "P4",
        "special-prize",
        runtime,
        core=True,
        current_stage="P10",
    )
    assert any("epoch" in error for error in errors)


def _provenance_runtime_and_content():
    executions = []
    artifacts = []
    reviewers = []
    for index, role in enumerate(sorted(SPECIAL_REVIEW_ROLES)):
        execution_id = f"exec_review_{index}"
        input_id = f"art_input_{index}"
        output_id = f"art_output_{index}"
        executions.append(
            {
                "entity_kind": "execution",
                "entity_id": execution_id,
                "payload": {
                    "status": "VALID",
                    "artifact_class": "production",
                    "stage": "P10",
                    "exit_code": 0,
                    "role": role,
                    "source_artifact_ids": [input_id],
                },
            }
        )
        artifacts.extend(
            [
                {
                    "entity_kind": "artifact",
                    "entity_id": input_id,
                    "payload": {"status": "VALID", "artifact_class": "external"},
                },
                {
                    "entity_kind": "artifact",
                    "entity_id": output_id,
                    "payload": {
                        "status": "VALID",
                        "artifact_class": "production",
                        "execution_id": execution_id,
                    },
                },
            ]
        )
        reviewers.append(
            {
                "role": role,
                "review_mode": "independent_agent",
                "execution_id": execution_id,
                "input_artifact_ids": [input_id],
                "output_artifact_ids": [output_id],
                "independence_checks": [
                    {"id": identifier, "status": "PASS"}
                    for identifier in ("distinct_execution", "input_closure", "blind_context", "post_p8")
                ],
            }
        )
    runtime = SimpleNamespace(
        registry=_StrictRegistry({"execution": executions, "artifact": artifacts})
    )
    return runtime, {"reviewers": reviewers, "limitations": ["角色独立性仍受执行环境约束"]}


def test_independent_provenance_requires_distinct_real_executions():
    runtime, content = _provenance_runtime_and_content()
    assert _validate_independent_provenance(content, runtime) == []
    content["reviewers"][1]["execution_id"] = content["reviewers"][0]["execution_id"]
    errors = _validate_independent_provenance(content, runtime)
    assert any("distinct" in error or "duplicated" in error for error in errors)


@pytest.mark.parametrize("bad_role", [[], {}, ["competition_judge"]])
def test_independent_provenance_rejects_unhashable_role_without_raising(bad_role):
    runtime, content = _provenance_runtime_and_content()
    content["reviewers"][0]["role"] = bad_role

    errors = _validate_independent_provenance(content, runtime)

    assert any("invalid" in error for error in errors)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_artifact_ids", [[]]),
        ("output_artifact_ids", [{}]),
    ],
)
def test_independent_provenance_rejects_non_string_artifact_ids_without_raising(field, value):
    runtime, content = _provenance_runtime_and_content()
    content["reviewers"][0][field] = value

    errors = _validate_independent_provenance(content, runtime)

    assert any("artifact IDs" in error for error in errors)


def test_independent_provenance_rejects_malformed_execution_sources_without_raising():
    runtime, content = _provenance_runtime_and_content()
    execution_id = content["reviewers"][0]["execution_id"]
    runtime.registry.records_by_kind["execution"][0]["payload"]["source_artifact_ids"] = [{}]

    errors = _validate_independent_provenance(content, runtime)

    assert any("source_artifact_ids" in error for error in errors)


def test_independent_provenance_rejects_malformed_check_entries_without_raising():
    runtime, content = _provenance_runtime_and_content()
    content["reviewers"][0]["independence_checks"] = [{"id": []}, []]

    errors = _validate_independent_provenance(content, runtime)

    assert any("independence_checks" in error for error in errors)


def test_not_applicable_alternatives_require_string_ids_and_valid_evidence():
    runtime, content = _provenance_runtime_and_content()
    content["alternative_evidence_ids"] = [[]]
    content["applicability"] = "NOT_APPLICABLE"
    content["not_applicable_reason"] = "该项不适用于当前题目"
    content["alternative_evidence_ids"] = [[]]

    errors = _validate_special_assessment(content, runtime=runtime)

    assert any("alternative_evidence_ids" in error for error in errors)


def test_malformed_applicability_and_guarantee_values_return_errors_without_raising():
    runtime, content = _strict_runtime_for_assessment()
    content["applicability"] = []
    content["cannot_guarantee"] = [{}]

    errors = _validate_special_assessment(
        content,
        json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))["profiles"]["special-prize"],
        runtime,
    )

    assert any("applicability" in error for error in errors)
    assert any("cannot_guarantee" in error for error in errors)


@pytest.mark.parametrize("bad_level", [[], {}, ["SPECIAL_PRIZE_CANDIDATE"]])
def test_special_assessment_rejects_unhashable_level_without_raising(bad_level):
    runtime, content = _strict_runtime_for_assessment()
    content["level"] = bad_level
    policy = json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))

    errors = _validate_special_assessment(content, policy["profiles"]["special-prize"], runtime)

    assert any("invalid level" in error for error in errors)


def test_independent_provenance_rejects_unhashable_review_mode_without_raising():
    runtime, content = _provenance_runtime_and_content()
    content["reviewers"][0]["review_mode"] = {}

    errors = _validate_independent_provenance(content, runtime)

    assert any("not independently executed" in error for error in errors)


def test_quality_contract_reports_invalid_runtime_contract_without_raising():
    runtime = SimpleNamespace(contract=[], registry=SimpleNamespace(iter_latest=lambda _kind: []))

    result = quality_contract_check(runtime, "P0")

    assert result.status == "ERROR"
    assert "contract" in result.reason


def test_quality_contract_reports_registry_runtime_error_without_raising():
    def broken_iter_latest(_kind):
        raise TypeError("registry payload is corrupted")

    runtime = SimpleNamespace(
        contract={"quality_profile": "deep-insight"},
        registry=SimpleNamespace(iter_latest=broken_iter_latest),
        workflow=SimpleNamespace(
            snapshot=lambda: {
                "stage_epochs": {f"P{i}": 1 for i in range(12)},
                "stages": {"P0": "ACTIVE"},
            }
        ),
    )

    result = quality_contract_check(runtime, "P0")

    assert result.status == "ERROR"
    assert "runtime error" in result.reason


def test_special_assessment_reports_malformed_workflow_snapshot_without_raising():
    runtime, content = _strict_runtime_for_assessment()
    runtime.workflow.snapshot = lambda: []
    policy = json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))

    errors = _validate_special_assessment(content, policy["profiles"]["special-prize"], runtime)

    assert any("workflow snapshot" in error for error in errors)


def test_independent_provenance_reports_malformed_workflow_stages_without_raising():
    runtime, content = _provenance_runtime_and_content()
    runtime.skill_root = ROOT
    runtime.workflow = SimpleNamespace(snapshot=lambda: {"stages": []})

    errors = _validate_independent_provenance(content, runtime)

    assert any("workflow stages" in error or "post-P8" in error for error in errors)


DEPTH_TYPES = [
    "theorem_application_record",
    "candidate_rejection_record",
    "formula_validity_record",
    "innovation_ablation_record",
    "counterintuitive_finding_record",
    "cross_problem_framework_record",
    "mechanism_explanation_record",
    "negative_result_record",
    "paper_depth_review",
    "special_prize_quality_assessment",
]


def test_depth_dependency_fields_declare_content_references():
    schemas = json.loads((POLICY_DIR / "schemas-v1.json").read_text("utf-8"))
    dependency_fields = schemas["evidence_dependency_fields"]
    generic = {
        "source_entity_ids[]",
        "supported_claim_ids[]",
        "alternative_evidence_ids[]",
    }
    for evidence_type in DEPTH_TYPES:
        declared = set(dependency_fields.get(evidence_type, []))
        missing = generic - declared
        assert not missing, f"{evidence_type} lacks dependency paths: {sorted(missing)}"
    assessment_paths = set(dependency_fields["special_prize_quality_assessment"])
    assert "criterion_results[].evidence_ids[]" in assessment_paths


def test_not_applicable_requires_structured_detail_fields():
    runtime, content = _provenance_runtime_and_content()
    content["applicability"] = "NOT_APPLICABLE"
    content["not_applicable_reason"] = "该项不适用于当前题目"
    content["alternative_evidence_ids"] = ["ev_alt"]

    errors = _validate_special_assessment(content, runtime=runtime)

    assert any("not_applicable_detail" in error for error in errors)

    content["not_applicable_detail"] = {
        "basis": "  ",
        "quality_impact": "",
        "alternative_required": "yes",
    }

    errors = _validate_special_assessment(content, runtime=runtime)

    assert any("not_applicable_detail.basis" in error for error in errors)
    assert any("not_applicable_detail.quality_impact" in error for error in errors)
    assert any("not_applicable_detail.alternative_required" in error for error in errors)


def test_not_applicable_detail_alternative_required_false_forbids_alternatives():
    runtime, content = _strict_runtime_for_assessment()
    profile = json.loads((POLICY_DIR / "quality-profiles-v1.json").read_text("utf-8"))[
        "profiles"
    ]["special-prize"]
    content["applicability"] = "NOT_APPLICABLE"
    content["not_applicable_reason"] = "该项不适用于当前题目"
    content["not_applicable_detail"] = {
        "basis": "题目为单问结构，不存在小问间共享变量",
        "quality_impact": "跨问迁移维度不计分，由退化验证替代覆盖",
        "alternative_required": False,
    }
    content["alternative_evidence_ids"] = ["ev_alt"]

    errors = _validate_special_assessment(content, profile, runtime)

    assert any("alternative_required is false" in error for error in errors)

    content["alternative_evidence_ids"] = []

    errors = _validate_special_assessment(content, profile, runtime)

    assert errors == []


def test_depth_evidence_supports_must_match_declared_content_dependencies(tmp_path):
    from helpers import STAGE_BUILDERS, p0_evidence
    from scripts.mmflow_core.errors import IntegrityError
    from scripts.mmflow_core.project import initialize_project

    runtime = initialize_project(
        tmp_path / "project", "CUMCM", "2026A", skill_root=ROOT
    )
    begin(runtime, "P0")
    p0_evidence(runtime)
    assert gate(runtime, "P0")["status"] == "PASS"
    advance(runtime, "P0")
    for stage in ("P1", "P2", "P3"):
        begin(runtime, stage)
        STAGE_BUILDERS[stage](runtime)
        assert gate(runtime, stage)["status"] == "PASS"
        advance(runtime, stage)
    begin(runtime, "P4")
    p4_evidence(runtime)

    content = _common_content()
    content["candidates"] = [
        {"id": "m1", "decision": "REJECT", "quantitative_reason": "验证误差更高"}
    ]
    with pytest.raises(IntegrityError, match="dependency mismatch"):
        reg(
            runtime,
            "evidence",
            {
                "evidence_id": "ev_depth_mismatch",
                "evidence_type": "candidate_rejection_record",
                "status": "VALID",
                "content": {**content, "source_entity_ids": ["art_rule"]},
                "supports": [],
            },
            stage="P4",
        )

    entity = reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_depth_bound",
            "evidence_type": "candidate_rejection_record",
            "status": "VALID",
            "content": {**content, "source_entity_ids": ["art_rule"]},
            "supports": ["art_rule"],
        },
        stage="P4",
    )
    assert entity["entity_id"] == "ev_depth_bound"

    from scripts.mmflow_core.lineage import LineageGraph

    graph = LineageGraph(runtime.registry)
    assert "ev_depth_bound" in graph.descendants(["art_rule"])
