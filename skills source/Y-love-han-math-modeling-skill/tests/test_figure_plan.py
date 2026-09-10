from __future__ import annotations

from scripts.mmflow_core.figure_plan import build_figure_plan, verify_figure_coverage


def test_prediction_contract_expands_required_roles_and_traits():
    contract = {
        "questions": [
            {
                "question_id": "Q1",
                "question_type": "prediction",
                "data_roles": ["raw", "clean", "split"],
                "model_families": ["baseline", "main"],
                "validation_traits": ["temporal_backtest", "residual_diagnostics", "sensitivity"],
            }
        ]
    }
    plan = build_figure_plan(contract, {"results": ["res_q1"]})
    roles = {item["role"] for item in plan["items"] if item["question_id"] == "Q1"}
    assert {"data_overview", "preprocessing", "model_result", "validation", "sensitivity"} <= roles
    assert all(item["necessity"] == "required" for item in plan["items"] if item["question_id"] == "Q1")
    assert plan["questions"] == ["Q1"]


def test_coverage_reports_missing_production_roles_without_making_up_questions():
    contract = {"questions": []}
    plan = build_figure_plan(contract, {})
    assert plan["items"] == []
    assert plan["questions"] == []
    report = verify_figure_coverage(plan, [])
    assert report["status"] == "PASS"


def test_coverage_blocks_required_role_without_real_result_bound_figure():
    contract = {"questions": [{"question_id": "Q2", "figure_roles": ["model_result"]}]}
    plan = build_figure_plan(contract, {"results": ["res_q2"]})
    report = verify_figure_coverage(plan, [{"question_id": "Q2", "role": "model_result", "status": "VALID", "source_results": []}])
    assert report["status"] == "FAIL"
    assert report["missing"] == [{"question_id": "Q2", "role": "model_result"}]


def test_question_scoped_results_cannot_be_reused_by_another_question():
    contract = {
        "questions": [
            {"question_id": "Q1", "figure_roles": ["model_result"]},
            {"question_id": "Q2", "figure_roles": ["model_result"]},
        ]
    }
    plan = build_figure_plan(
        contract,
        {
            "results": ["res_q1", "res_q2"],
            "results_by_question": {"Q1": ["res_q1"], "Q2": ["res_q2"]},
        },
    )
    report = verify_figure_coverage(
        plan,
        [
            {
                "question_id": "Q1",
                "role": "model_result",
                "status": "VALID",
                "artifact_class": "production",
                "backend": "python",
                "source_results": ["res_q1"],
                "information_gain": "compares the model with the required baseline",
            },
            {
                "question_id": "Q2",
                "role": "model_result",
                "status": "VALID",
                "artifact_class": "production",
                "backend": "python",
                "source_results": ["res_q1"],
                "information_gain": "would be valid only if it used Q2 results",
            },
        ],
    )
    assert report["status"] == "FAIL"
    assert report["missing"] == [{"question_id": "Q2", "role": "model_result"}]
