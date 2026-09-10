from __future__ import annotations

from typing import Any, Callable

from .errors import ConfigError


TRAIT_ADAPTERS = {
    "temporal": {"temporal_backtest"},
    "grouped": {"grouped_split"},
    "spatial": {"spatial_validation"},
    "repeated_measures": {"subject_level_split"},
    "stochastic": {"stochastic_convergence"},
    "constrained": {"constraint_feasibility"},
    # R24 题型盲区补全：成像/光谱/音频类赛题的领域验证适配器
    # （trait 声明 image/signal 时在 P6 要求对应领域一致性检查）。
    "image": {"image_domain_validation"},
    "signal": {"signal_domain_validation"},
}

CLAIM_ADAPTERS = {
    "forecast": {"baseline_comparison", "leakage_audit", "forecast_backtest"},
    "probabilistic_forecast": {
        "baseline_comparison",
        "leakage_audit",
        "forecast_backtest",
        "calibration_coverage",
    },
    "causal": {"causal_identification"},
    "optimization_recommendation": {
        "constraint_feasibility",
        "optimality_evidence",
        "scenario_sensitivity",
    },
    "global_optimum": {"constraint_feasibility", "certified_optimality_evidence"},
    "parameter_estimate": {"identifiability_uncertainty"},
    "scenario": {"program_and_model_validation", "uncertainty_scope"},
    "ranking": {"weight_and_rank_reversal_sensitivity"},
    "spatial_prediction": {"spatial_validation", "leakage_audit"},
    "theoretical": {"assumption_and_boundary_verification"},
}

MODEL_ADAPTERS = {
    "pde": {"grid_convergence"},
    "ode": {"timestep_convergence"},
    "heuristic_optimization": {"multiseed_budget_match", "small_instance_or_bound"},
    "exact_optimization": {"constraint_feasibility", "solver_status_and_gap"},
    "multiobjective_optimization": {"pareto_stability"},
    "simulation": {"program_and_model_validation", "stochastic_convergence"},
    "surrogate_model": {"surrogate_validation", "uncertainty_scope"},
    "clustering": {"cluster_stability"},
    "network": {"network_construction_robustness"},
    "composite_evaluation": {"weight_and_rank_reversal_sensitivity"},
    "analytic_model": {
        "assumption_and_boundary_verification",
        "limiting_case_check",
    },
}


def _analytic_grid_waiver(contract: dict[str, Any]) -> bool:
    properties = contract.get("properties", {})
    return (
        properties.get("solver_type") == "analytic"
        and isinstance(properties.get("exact_solution_evidence"), str)
        and bool(properties["exact_solution_evidence"])
    )


def _deterministic_multiseed_waiver(contract: dict[str, Any]) -> bool:
    return contract.get("properties", {}).get("algorithm_randomized") is False


WAIVER_RULES: dict[str, tuple[str, Callable[[dict[str, Any]], bool]]] = {
    "NA-GRID-ANALYTIC-001": ("grid_convergence", _analytic_grid_waiver),
    "NA-MULTISEED-DETERMINISTIC-001": (
        "multiseed_budget_match",
        _deterministic_multiseed_waiver,
    ),
}


def _string_set(contract: dict[str, Any], key: str) -> set[str]:
    value = contract.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"problem contract {key} must be a list of strings")
    return set(value)


def required_adapters(problem_contract: dict[str, Any]) -> set[str]:
    if not isinstance(problem_contract.get("problem_id"), str) or not problem_contract[
        "problem_id"
    ]:
        raise ConfigError("problem contract requires problem_id")
    properties = problem_contract.get("properties", {})
    if not isinstance(properties, dict):
        raise ConfigError("problem contract properties must be an object")
    required: set[str] = set()
    for trait in _string_set(problem_contract, "traits"):
        if trait not in TRAIT_ADAPTERS:
            raise ConfigError(f"unknown problem contract trait: {trait}")
        required.update(TRAIT_ADAPTERS[trait])
    for claim in _string_set(problem_contract, "claim_types"):
        if claim not in CLAIM_ADAPTERS:
            raise ConfigError(f"unknown problem contract claim type: {claim}")
        required.update(CLAIM_ADAPTERS[claim])
    for family in _string_set(problem_contract, "model_families"):
        if family not in MODEL_ADAPTERS:
            raise ConfigError(f"unknown problem contract model family: {family}")
        required.update(MODEL_ADAPTERS[family])
    return required


def validate_adapter_coverage(
    problem_contract: dict[str, Any],
    completed: dict[str, str],
    waivers: dict[str, dict[str, Any]],
    evidence_resolver: Callable[[str], bool],
) -> dict[str, Any]:
    if not isinstance(completed, dict) or not isinstance(waivers, dict):
        raise ConfigError("completed adapters and waivers must be objects")
    required = required_adapters(problem_contract)
    statuses: dict[str, str] = {}
    invalid: list[str] = []
    for adapter in sorted(required):
        if completed.get(adapter) == "PASS":
            statuses[adapter] = "PASS"
            continue
        waiver = waivers.get(adapter)
        if not isinstance(waiver, dict):
            statuses[adapter] = "FAIL"
            invalid.append(adapter)
            continue
        rule_id = waiver.get("rule_id")
        evidence = waiver.get("evidence")
        rule = WAIVER_RULES.get(rule_id)
        if (
            rule is None
            or rule[0] != adapter
            or not isinstance(evidence, list)
            or not evidence
            or not all(isinstance(item, str) and item for item in evidence)
            or not all(evidence_resolver(item) for item in evidence)
            or not rule[1](problem_contract)
        ):
            statuses[adapter] = "FAIL"
            invalid.append(adapter)
            continue
        statuses[adapter] = "NOT_APPLICABLE"
    return {
        "status": "PASS" if not invalid else "FAIL",
        "required": sorted(required),
        "adapters": statuses,
        "missing_or_invalid": invalid,
    }
