"""Question-adaptive production figure coverage planning."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


BASE_ROLES = ("data_overview", "preprocessing", "model_result", "validation")
TRAIT_ROLES = {
    "sensitivity": "sensitivity",
    "uncertainty": "uncertainty",
    "uncertainty_quantification": "uncertainty",
    "constraint_tradeoff": "pareto",
    "pareto": "pareto",
    "scenario": "scenario",
    "what_if": "scenario",
    "mechanism": "mechanism",
    "spatial": "spatial",
    "network": "network",
}


def _question_list(contract: dict[str, Any]) -> list[dict[str, Any]]:
    questions = contract.get("questions", [])
    if not isinstance(questions, list):
        raise ValueError("problem contract questions must be a list")
    normalized: list[dict[str, Any]] = []
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("each problem contract question must be an object")
        question_id = question.get("question_id")
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError("each question requires a non-empty question_id")
        normalized.append(question)
    return normalized


def _roles_for(question: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    explicit = question.get("figure_roles")
    if explicit is None:
        roles = list(BASE_ROLES)
    elif isinstance(explicit, list) and all(isinstance(item, str) and item for item in explicit):
        roles = list(dict.fromkeys(explicit))
    else:
        raise ValueError("figure_roles must be a list of strings")
    reasons: dict[str, str] = {}
    for role in BASE_ROLES:
        if role in roles:
            reasons[role] = "required by every question for data/model/validation traceability"
    traits = question.get("validation_traits", [])
    if not isinstance(traits, list):
        raise ValueError("validation_traits must be a list")
    for trait in traits:
        if trait not in TRAIT_ROLES:
            continue
        role = TRAIT_ROLES[trait]
        if role not in roles:
            roles.append(role)
        reasons[role] = f"required by validation trait: {trait}"
    return roles, reasons


def build_figure_plan(
    contract: dict[str, Any],
    registry_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic plan without inventing data, results or claims."""
    registry_snapshot = registry_snapshot or {}
    if not isinstance(registry_snapshot, dict):
        raise ValueError("registry_snapshot must be an object")
    registered_results = registry_snapshot.get("results", [])
    if not isinstance(registered_results, list) or not all(
        isinstance(item, str) and item for item in registered_results
    ):
        raise ValueError("registry_snapshot results must be a list of IDs")
    results_by_question = registry_snapshot.get("results_by_question", {})
    if results_by_question is None:
        results_by_question = {}
    if not isinstance(results_by_question, dict) or any(
        not isinstance(question_id, str)
        or not isinstance(result_ids, list)
        or not all(isinstance(item, str) and item for item in result_ids)
        for question_id, result_ids in results_by_question.items()
    ):
        raise ValueError("registry_snapshot results_by_question must map IDs to lists")
    # A question-scoped result list is authoritative when present.  The global
    # list remains a backwards-compatible fallback for older snapshots.
    def result_ids_for(question_id: str) -> list[str]:
        if results_by_question:
            # Once a question-scoped map is supplied, an omitted question has
            # no declared results.  Falling back to another question's global
            # pool would make cross-question evidence appear valid.
            return list(dict.fromkeys(results_by_question.get(question_id, [])))
        return list(dict.fromkeys(registered_results))
    items: list[dict[str, Any]] = []
    questions: list[str] = []
    for question in _question_list(contract):
        question_id = question["question_id"]
        questions.append(question_id)
        roles, reasons = _roles_for(question)
        hero_role = question.get("hero_figure_role")
        if hero_role is not None and (
            not isinstance(hero_role, str) or not hero_role.strip()
        ):
            raise ValueError("hero_figure_role must be a non-empty string")
        hero_role = hero_role.strip() if isinstance(hero_role, str) else None
        if hero_role is not None and hero_role not in roles:
            raise ValueError(
                f"hero_figure_role {hero_role!r} is not among planned roles "
                f"{roles}; add it to figure_roles/validation_traits first"
            )
        question_results = result_ids_for(question_id)
        for role in roles:
            item = {
                "question_id": question_id,
                "role": role,
                "necessity": "required",
                "reason": reasons.get(role, "declared by problem contract"),
                "source_requirements": {
                    "result_ids": question_results,
                    "results_declared": True,
                    "production_only": True,
                },
                "generation": "python_baseline",
            }
            if role == hero_role:
                # 图表叙事线锚点：一图讲完该问答案的综合图（评委 30 秒
                # 获得核心信息的入口）；verify 不因 hero 标记改变判定，
                # 仅作为 P8 写作与答辩动线的机器可读提示。
                item["hero"] = True
            items.append(item)
        for role in question.get("optional_figure_roles", []) or []:
            if isinstance(role, str) and role and role not in roles:
                items.append(
                    {
                        "question_id": question_id,
                        "role": role,
                        "necessity": "optional",
                        "reason": "explicitly declared optional role",
                        "source_requirements": {
                            "result_ids": question_results,
                            "results_declared": True,
                            "production_only": True,
                        },
                        "generation": "python_baseline",
                    }
                )
        for decision in question.get("not_applicable_figure_roles", []) or []:
            if (
                isinstance(decision, dict)
                and isinstance(decision.get("role"), str)
                and decision.get("role")
                and str(decision.get("reason", "")).strip()
            ):
                items.append(
                    {
                        "question_id": question_id,
                        "role": str(decision["role"]),
                        "necessity": "not_applicable",
                        "not_applicable_reason": str(decision["reason"]),
                        "source_requirements": {
                            "result_ids": [],
                            "results_declared": False,
                            "production_only": True,
                        },
                        "generation": "none",
                    }
                )
    return {
        "schema": "mmflow-figure-coverage-plan/v1",
        "questions": questions,
        "items": items,
        "registry_snapshot": registry_snapshot,
    }


def _valid_figure(figure: dict[str, Any], item: dict[str, Any]) -> bool:
    if not isinstance(figure, dict) or figure.get("status") != "VALID":
        return False
    if figure.get("question_id") != item["question_id"] or figure.get("role") != item["role"]:
        return False
    if figure.get("source_result_question_mismatch"):
        return False
    sources = figure.get("source_results")
    if not isinstance(sources, list) or not sources:
        return False
    # A plan may carry the expected Result IDs.  Do not accept a figure that
    # merely points to any arbitrary result from another question/run.
    requirements = item.get("source_requirements", {})
    expected = requirements.get("result_ids", [])
    if requirements.get("results_declared") and not expected:
        return False
    if expected and not set(sources).issubset(set(expected)):
        return False
    if figure.get("backend") not in {"python", "matlab"}:
        return False
    # Coverage is evaluated from Registry payloads.  A missing class is only
    # tolerated by the standalone planner API for backwards-compatible
    # fixtures; once a plan is consumed as production evidence, the payload
    # must explicitly identify a production figure.
    if figure.get("artifact_class") != "production":
        return False
    if not isinstance(figure.get("information_gain"), str) or not figure["information_gain"].strip():
        return False
    return True


def verify_figure_coverage(
    plan: dict[str, Any], figures: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    items = plan.get("items", []) if isinstance(plan, dict) else []
    figure_list = list(figures)
    missing: list[dict[str, str]] = []
    satisfied: list[dict[str, str]] = []
    not_applicable: list[dict[str, str]] = []
    for item in items:
        matches = [figure for figure in figure_list if _valid_figure(figure, item)]
        target = {"question_id": item["question_id"], "role": item["role"]}
        if item.get("necessity") == "not_applicable":
            # A plan item may carry a structured, justified not-applicable
            # decision (e.g. a theoretical question with no data-overview
            # evidence).  It is recorded, never counted as satisfied and
            # never blocks coverage; the reason stays auditable in the plan.
            not_applicable.append(
                {
                    **target,
                    "reason": str(item.get("not_applicable_reason", "")),
                }
            )
        elif matches or item.get("necessity") == "optional":
            if matches:
                satisfied.append(target)
        else:
            missing.append(target)
    return {
        "schema": "mmflow-figure-coverage-report/v1",
        "status": "PASS" if not missing else "FAIL",
        "required_count": sum(item.get("necessity") == "required" for item in items),
        "satisfied": satisfied,
        "missing": missing,
        "not_applicable": not_applicable,
    }
