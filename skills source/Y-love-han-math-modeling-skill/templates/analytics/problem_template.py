# -*- coding: utf-8 -*-
"""通用问题求解参考模板。

本文件是可运行的 reference/template，不是任何具体赛题的生产解法。
它提供一个小型数值回归基线，帮助建立“数据→模型→求解→验证→不确定性→
结果保存”的接口闭环。使用真实竞赛数据前，必须替换题目识别、变量定义、
假设、公式、约束、算法和验证设计，并在 mmflow Registry 中登记生产证据。
示例输出永远不能直接升级为 production 证据或论文结论。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from utils import (
    OUTPUT_DIR,
    RNG,
    bootstrap_ci,
    confidence_interval,
    load_data,
    save_csv,
    save_fig,
)


REFERENCE_ONLY = True


def _numeric_frame(data: Any) -> pd.DataFrame:
    """Convert common input forms to a finite numeric frame."""
    if isinstance(data, pd.DataFrame):
        frame = data.copy()
    elif isinstance(data, dict):
        frame = pd.DataFrame(data)
    else:
        array = np.asarray(data)
        if array.ndim != 2:
            raise ValueError("data must be a DataFrame, mapping, or two-dimensional array")
        frame = pd.DataFrame(array)
    numeric = frame.select_dtypes(include=[np.number]).copy()
    if numeric.shape[1] < 2:
        raise ValueError("at least two numeric columns are required: predictors and target")
    numeric = numeric.replace([np.inf, -np.inf], np.nan).dropna(axis=0, how="any")
    if len(numeric) < 3:
        raise ValueError("at least three complete numeric observations are required")
    return numeric.reset_index(drop=True)


def _design_and_target(data: Any, model: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    frame = _numeric_frame(data)
    columns = [str(item) for item in model.get("numeric_columns", frame.columns)]
    columns = [item for item in columns if item in frame.columns]
    if len(columns) < 2:
        columns = [str(item) for item in frame.columns]
    target_name = str(model.get("target_column", columns[-1]))
    if target_name not in frame.columns:
        target_name = str(frame.columns[-1])
    feature_names = [item for item in columns if item != target_name]
    if not feature_names:
        raise ValueError("the selected target leaves no predictor")
    x = frame[feature_names].to_numpy(dtype=float)
    y = frame[target_name].to_numpy(dtype=float)
    return x, y, feature_names


def _fit_least_squares(x: np.ndarray, y: np.ndarray, *, intercept: bool = True,
                       ridge_alpha: float = 0.0) -> tuple[np.ndarray, np.ndarray, float]:
    design = np.column_stack([np.ones(len(x)), x]) if intercept else x
    alpha = max(float(ridge_alpha), 0.0)
    if alpha > 0:
        penalty = np.eye(design.shape[1])
        if intercept:
            penalty[0, 0] = 0.0
        coefficients = np.linalg.solve(
            design.T @ design + alpha * penalty,
            design.T @ y,
        )
    else:
        coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    predicted = design @ coefficients
    condition = float(np.linalg.cond(design)) if design.size else float("inf")
    return coefficients, predicted, condition


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    residuals = actual - predicted
    sse = float(np.sum(residuals ** 2))
    total = float(np.sum((actual - np.mean(actual)) ** 2))
    return {
        "RMSE": float(np.sqrt(np.mean(residuals ** 2))),
        "MAE": float(np.mean(np.abs(residuals))),
        "R2": float(1.0 - sse / max(total, 1e-12)),
        "residual_mean": float(np.mean(residuals)),
        "residual_std": float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0,
    }


def _finite_scalar(value: Any) -> float:
    number = float(value)
    if not np.isfinite(number):
        raise ValueError("model output must be finite")
    return number


def _metric_value(output: Any, metric_key: str | None = None) -> float:
    if isinstance(output, dict):
        if metric_key is not None and metric_key in output:
            return _finite_scalar(output[metric_key])
        for key in ("RMSE", "rmse", "MAE", "mae", "R2", "r2"):
            if key in output:
                return _finite_scalar(output[key])
        for value in output.values():
            if isinstance(value, (int, float, np.integer, np.floating)):
                return _finite_scalar(value)
        raise ValueError("model output has no numeric metric")
    return _finite_scalar(output)


def model_building(data: Any) -> tuple[dict[str, Any], dict[str, float]]:
    """Construct a transparent OLS reference model and numerical controls.

    The target is the last numeric column unless a project-specific adapter
    changes ``model['target_column']`` after inspecting the problem contract.
    The returned parameters are deliberately small, explicit controls for the
    reference uncertainty routine; they are not claims about a real problem.
    """
    frame = _numeric_frame(data)
    numeric_columns = [str(item) for item in frame.columns]
    target = numeric_columns[-1]
    features = numeric_columns[:-1]
    x = frame[features].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    model = {
        "schema": "mmflow-problem-reference-model/v1",
        "model_family": "ordinary_least_squares",
        "numeric_columns": numeric_columns,
        "feature_columns": features,
        "target_column": target,
        "intercept": True,
        "sample_size": int(len(frame)),
        "feature_count": int(len(features)),
        "design_rank": int(np.linalg.matrix_rank(design)),
        "condition_number": float(np.linalg.cond(design)),
        "assumptions": [
            "complete finite paired observations after explicit row filtering",
            "a linear relation is used only as a diagnostic reference",
            "the observed sample is not assumed to identify causal effects",
        ],
        "validity_checks": [
            "target and predictor units must be documented by the problem adapter",
            "rank deficiency and ill-conditioning must be reported",
            "extrapolation beyond the observed feature domain is not endorsed",
        ],
        "limitations": [
            "generic reference structure is not a competition-specific model",
            "no production claim is made without registered data, execution, and validation evidence",
        ],
    }
    params = {
        "calibration_scale": 1.0,
        "ridge_alpha": 1e-8,
    }
    return model, params


def theoretical_analysis(model_params: dict[str, Any]) -> dict[str, Any]:
    """Report applicable closed-form, rank, conditioning, and complexity facts."""
    if not isinstance(model_params, dict):
        raise TypeError("model_params must be the model dictionary returned by model_building")
    sample_size = int(model_params.get("sample_size", 0))
    feature_count = int(model_params.get("feature_count", 0))
    rank = int(model_params.get("design_rank", 0))
    condition = float(model_params.get("condition_number", np.inf))
    return {
        "status": "PASS" if sample_size > feature_count and rank >= min(feature_count + 1, sample_size) else "LIMITED",
        "applicability": "APPLICABLE",
        "closed_form_solution": "beta = argmin ||y - X beta||_2^2; solved by least squares or ridge-stabilized normal equations",
        "complexity": {
            "time": "O(n p^2 + p^3) for a dense p-column design",
            "space": "O(n p)",
            "n": sample_size,
            "p": feature_count + 1,
        },
        "rank": rank,
        "condition_number": condition,
        "conditioning_warning": bool(not np.isfinite(condition) or condition > 1e8),
        "error_scope": "residual metrics quantify in-sample approximation error only; they are not a generalization bound",
        "limitations": list(model_params.get("limitations", [])),
    }


def model_solving(data: Any, model: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Fit the reference model and return structured diagnostics."""
    started = time.perf_counter()
    x, y, feature_names = _design_and_target(data, model)
    intercept = bool(model.get("intercept", True))
    calibration = float(params.get("calibration_scale", 1.0))
    alpha = float(params.get("ridge_alpha", 1e-8))
    coefficients, fitted, condition = _fit_least_squares(
        x, y, intercept=intercept, ridge_alpha=alpha
    )
    fitted = fitted * calibration
    baseline = np.full_like(y, np.mean(y))
    metrics = _metrics(y, fitted)
    result: dict[str, Any] = {
        "schema": "mmflow-structured-reference-result/v1",
        "status": "PASS",
        "production_eligible": False,
        "reference_only": True,
        "metric_primary": "RMSE",
        **metrics,
        "baseline_RMSE": float(_metrics(y, baseline)["RMSE"]),
        "n": int(len(y)),
        "p": int(x.shape[1]),
        "coefficients": {
            ("intercept" if intercept and index == 0 else feature_names[index - 1] if intercept else feature_names[index]): float(value)
            for index, value in enumerate(coefficients)
        },
        "condition_number": condition,
        "calibration_scale": calibration,
        "ridge_alpha": alpha,
        "elapsed_seconds": float(time.perf_counter() - started),
        "observed": y.tolist(),
        "predicted": fitted.tolist(),
        "residuals": (y - fitted).tolist(),
        "limitations": list(model.get("limitations", [])),
    }
    return result


def ablation_study(data: Any, model: dict[str, Any], full_model_results: dict[str, Any]) -> dict[str, Any]:
    """Compare the full reference fit with a no-intercept alternative."""
    x, y, feature_names = _design_and_target(data, model)
    _, full_pred, _ = _fit_least_squares(x, y, intercept=True, ridge_alpha=0.0)
    _, reduced_pred, _ = _fit_least_squares(x, y, intercept=False, ridge_alpha=0.0)
    full_errors = np.abs(y - full_pred)
    reduced_errors = np.abs(y - reduced_pred)
    try:
        p_value = float(stats.ttest_rel(full_errors, reduced_errors, nan_policy="omit").pvalue)
    except Exception:
        p_value = float("nan")
    full_rmse = _metrics(y, full_pred)["RMSE"]
    reduced_rmse = _metrics(y, reduced_pred)["RMSE"]
    relative_change = 100.0 * (reduced_rmse - full_rmse) / max(abs(full_rmse), 1e-12)
    return {
        "status": "PASS",
        "reference_only": True,
        "full_model": {"intercept": True, "RMSE": float(full_rmse)},
        "without_intercept": {"intercept": False, "RMSE": float(reduced_rmse)},
        "relative_rmse_change_pct": float(relative_change),
        "paired_error_test_p_value": p_value,
        "conclusion": "the intercept effect is reported quantitatively; retain it only when the problem-specific assumptions and validation support it",
        "limitations": ["this is a structural reference ablation, not evidence of innovation for a real competition solution"],
        "full_result_primary_metric": full_model_results.get("RMSE"),
    }


def result_analysis(results: dict[str, Any], data: Any) -> dict[str, Any]:
    """Summarize fit quality and save a diagnostic figure when arrays are present."""
    observed = np.asarray(results.get("observed", []), dtype=float)
    predicted = np.asarray(results.get("predicted", []), dtype=float)
    if observed.size < 2 or observed.shape != predicted.shape:
        return {
            "status": "NOT_APPLICABLE",
            "reason": "structured observed/predicted arrays are required for diagnostic analysis",
            "reference_only": True,
        }
    residuals = observed - predicted
    _, ci_low, ci_high = bootstrap_ci(np.abs(residuals), n_bootstrap=1000)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].scatter(observed, predicted, alpha=0.75, color="#0072B2", label="reference fit")
    lo = float(min(observed.min(), predicted.min()))
    hi = float(max(observed.max(), predicted.max()))
    axes[0].plot([lo, hi], [lo, hi], color="#D55E00", linestyle="--", label="identity")
    axes[0].set_xlabel("Observed")
    axes[0].set_ylabel("Predicted")
    axes[0].legend(loc="upper left")
    axes[1].hist(residuals, bins=min(20, max(5, int(np.sqrt(len(residuals))))), color="#009E73", alpha=0.8)
    axes[1].axvline(0.0, color="#D55E00", linestyle="--", label="zero residual")
    axes[1].set_xlabel("Residual")
    axes[1].set_ylabel("Count")
    axes[1].legend(loc="upper left")
    fig.tight_layout()
    figure_path = save_fig(fig, "fig_reference_fit_diagnostics.png")
    plt.close(fig)
    return {
        "status": "PASS",
        "reference_only": True,
        "mean_absolute_error_ci95": [float(ci_low), float(ci_high)],
        "residual_quantiles": [float(item) for item in np.percentile(residuals, [2.5, 50, 97.5])],
        "figure_path": str(figure_path),
        "interpretation": "diagnostic approximation only; scientific meaning requires problem-specific units, mechanism, and validation",
    }


def uncertainty_quantification(
    params: dict[str, Any],
    model_func: Callable[..., Any],
    metric_key: str | None = None,
    *,
    n_bootstrap: int = 1000,
    model_variants: dict[str, Callable[[dict[str, Any]], Any]] | None = None,
    data: Any | None = None,
) -> dict[str, Any]:
    """Quantify declared parameter uncertainty and honestly report unavailable dimensions.

    Parameter uncertainty perturbs numeric controls in the declared ±20% range.
    Model uncertainty is computed only when callers provide named alternative
    model functions. Data uncertainty requires an explicit resampler callable
    or a model function that accepts a ``data`` keyword; otherwise it is
    returned as structured ``NOT_APPLICABLE`` rather than fabricated.
    """
    if not isinstance(n_bootstrap, int) or n_bootstrap < 2:
        raise ValueError("n_bootstrap must be an integer of at least two")
    numeric_params = {
        key: float(value)
        for key, value in params.items()
        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool)
    }
    perturbations: list[float] = []
    for _ in range(n_bootstrap):
        perturbed = {key: value * RNG.uniform(0.8, 1.2) for key, value in numeric_params.items()}
        try:
            perturbations.append(_metric_value(model_func(perturbed), metric_key))
        except Exception:
            continue
    param_ci = [float(np.percentile(perturbations, q)) for q in (2.5, 97.5)] if len(perturbations) >= 2 else [None, None]

    model_uncertainty: dict[str, Any]
    if model_variants:
        variant_values: dict[str, float] = {}
        for name, variant_func in model_variants.items():
            try:
                variant_values[str(name)] = _metric_value(variant_func(dict(numeric_params)), metric_key)
            except Exception as error:
                variant_values[str(name)] = float("nan")
        valid = [value for value in variant_values.values() if np.isfinite(value)]
        model_uncertainty = {
            "status": "PASS" if valid else "NOT_APPLICABLE",
            "values": variant_values,
            "range": [float(min(valid)), float(max(valid))] if valid else [None, None],
            "reason": "named alternative model functions were evaluated" if valid else "alternative model functions did not yield finite metrics",
        }
    else:
        model_uncertainty = {
            "status": "NOT_APPLICABLE",
            "reason": "model_func exposes one declared model; provide model_variants for structural alternatives",
        }

    data_uncertainty: dict[str, Any]
    if data is None:
        data_uncertainty = {
            "status": "NOT_APPLICABLE",
            "reason": "the template call did not provide a data object or explicit resampler",
        }
    else:
        data_uncertainty = {
            "status": "NOT_APPLICABLE",
            "reason": "data was supplied, but a resampling-aware model adapter is required to avoid silently changing the model contract",
        }
    return {
        "status": "PASS" if len(perturbations) >= 2 else "LIMITED",
        "reference_only": True,
        "parameter_uncertainty": {
            "ci95": param_ci,
            "n_requested": n_bootstrap,
            "n_valid": len(perturbations),
            "perturbation_factor": [0.8, 1.2],
        },
        "model_uncertainty": model_uncertainty,
        "data_uncertainty": data_uncertainty,
        "limitations": [
            "these intervals describe the declared reference adapter, not a validated uncertainty model for a contest problem",
            "NOT_APPLICABLE dimensions must be replaced by problem-specific evidence before scientific claims are made",
        ],
    }


def save_results(results: dict[str, Any], output_dir: Path | str = OUTPUT_DIR) -> dict[str, Any]:
    """Persist scalar metrics as CSV and the complete structured result as JSON."""
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    scalar_rows = []
    for key, value in results.items():
        if isinstance(value, (int, float, np.integer, np.floating)) and np.isfinite(float(value)):
            scalar_rows.append({"metric": key, "value": float(value)})
    csv_path = destination / "reference_results.csv"
    pd.DataFrame(scalar_rows, columns=["metric", "value"]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path = destination / "reference_results.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {
        "status": "PASS",
        "reference_only": True,
        "csv_path": str(csv_path),
        "json_path": str(json_path),
        "scalar_metric_count": len(scalar_rows),
    }


def solve(input_data: Any, config: dict[str, Any]) -> dict[str, Any]:
    """Controlled-runner entry point (mmflow-result-contract/v1).

    Mirrors templates/production/model_entry.py's expected
    ``solve(input_data, config)`` interface so this analytics template can be
    executed through ``mmflow run`` without glue code.  ``config`` keys:
    ``question_id``, ``metric_key`` (default RMSE), ``dataset_split_id``,
    ``scenario`` (default "reference"), ``direction`` (default
    lower_is_better), ``sample_size`` (default row count).  The emitted
    contract is reference output: it becomes production evidence only after a
    production-class controlled run and Registry registration.
    """
    model, params = model_building(input_data)
    results = model_solving(input_data, model, params)
    metric_key = str(config.get("metric_key", "RMSE"))
    value = _finite_scalar(_metric_value(results, metric_key))
    direction = str(config.get("direction", "lower_is_better"))
    scenario = str(config.get("scenario", "reference"))
    split_id = str(config.get("dataset_split_id", ""))
    if not split_id:
        raise ValueError(
            "config.dataset_split_id is required: register the split entity "
            "first and reference it in the run config dataset_split_ids"
        )
    default_sample_size = int(_numeric_frame(input_data).shape[0])
    sample_size = int(config.get("sample_size") or default_sample_size)
    return {
        "schema": "mmflow-result-contract/v1",
        "results": {
            str(config.get("result_key", f"q{config.get('question_id', '1')}")): {
                "model_id": str(config.get("model_id", "reference_ols")),
                "metric": metric_key,
                "value": value,
                "unit": str(config.get("unit", "dimensionless")),
                "direction": direction,
                "scenario": scenario,
                "dataset_split_id": split_id,
                "sample_size": sample_size,
            }
        },
        "diagnostics": {
            "status": "PASS",
            "reference_only": True,
            "metrics_all": {key: val for key, val in results.items()
                            if isinstance(val, (int, float)) and np.isfinite(float(val))},
        },
    }


if __name__ == "__main__":
    example = pd.DataFrame({
        "x1": np.linspace(0.0, 1.0, 24),
        "x2": np.linspace(1.0, 2.0, 24) ** 2,
        "y": 1.0 + 0.8 * np.linspace(0.0, 1.0, 24) + 0.1 * np.sin(np.arange(24)),
    })
    model, params = model_building(example)
    theory = theoretical_analysis(model)
    results = model_solving(example, model, params)
    ablation = ablation_study(example, model, results)
    analysis = result_analysis(results, example)
    uncertainty = uncertainty_quantification(
        params, lambda candidate: model_solving(example, model, candidate), metric_key="RMSE"
    )
    saved = save_results({**results, "theory": theory, "ablation": ablation, "analysis": analysis, "uncertainty": uncertainty})
    print(json.dumps(saved, ensure_ascii=False, indent=2))
