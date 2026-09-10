"""Small, dependency-light reference pipeline.

This is a runnable demonstration of the template contract, not production
evidence and not a solution to any competition problem.  It demonstrates a
baseline, a fitted linear model, residual diagnostics, a simple ablation and
two uncertainty sources without pretending that one generic model fits every
problem type.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "math-modeling-reference-result/v1"


def make_reference_data(n: int = 40) -> dict[str, list[float]]:
    if n < 8:
        raise ValueError("reference data requires at least eight rows")
    x = np.linspace(0.0, 1.0, n)
    y = 1.5 + 2.0 * x + 0.08 * np.sin(8.0 * x)
    return {"x": x.tolist(), "y": y.tolist()}


def _arrays(data: dict[str, list[float]]) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(data.get("x", []), dtype=float)
    y = np.asarray(data.get("y", []), dtype=float)
    if x.ndim != 1 or y.ndim != 1 or len(x) != len(y) or len(x) < 8:
        raise ValueError("reference data must contain equal one-dimensional x/y arrays")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("reference data must be finite")
    return x, y


def _fit(x: np.ndarray, y: np.ndarray, *, intercept: bool = True) -> tuple[np.ndarray, np.ndarray]:
    design = np.column_stack([np.ones_like(x), x]) if intercept else x[:, None]
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    return coefficients, design @ coefficients


def _rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def run_reference_pipeline(data: dict[str, list[float]], output_dir: Path | str) -> dict[str, Any]:
    x, y = _arrays(data)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    coefficients, fitted = _fit(x, y)
    baseline_prediction = np.full_like(y, np.mean(y))
    no_intercept_coefficients, no_intercept_fitted = _fit(x, y, intercept=False)
    model = {
        "family": "ordinary_least_squares",
        "equation": "y = beta0 + beta1*x",
        "coefficients": {"beta0": float(coefficients[0]), "beta1": float(coefficients[1])},
        "assumptions": ["finite paired observations", "linear approximation is a diagnostic baseline"],
        "limitations": ["does not claim causal validity or extrapolation safety"],
    }
    residuals = y - fitted
    theory = {
        "complexity": "O(n)",
        "identifiability_check": bool(np.ptp(x) > 0),
        "residual_mean": float(np.mean(residuals)),
        "residual_std": float(np.std(residuals, ddof=1)),
        "condition_warning": bool(np.ptp(x) < 1e-8),
    }
    results = {
        "rmse": _rmse(y, fitted),
        "baseline_rmse": _rmse(y, baseline_prediction),
        "sample_size": int(len(y)),
        "r2_like": float(1.0 - np.sum(residuals**2) / max(np.sum((y - np.mean(y))**2), 1e-12)),
    }
    ablation = {
        "status": "PASS" if _rmse(y, fitted) <= _rmse(y, no_intercept_fitted) else "INFORMATIVE",
        "full_rmse": _rmse(y, fitted),
        "without_intercept_rmse": _rmse(y, no_intercept_fitted),
        "conclusion": "intercept contribution is reported quantitatively; do not assume it is universally useful",
    }
    rng = np.random.default_rng(20260806)
    bootstrap = []
    for _ in range(400):
        indices = rng.integers(0, len(x), len(x))
        boot_coef, _ = _fit(x[indices], y[indices])
        bootstrap.append(_rmse(y, boot_coef[0] + boot_coef[1] * x))
    perturb = []
    for scale in (0.98, 1.02):
        perturbed_coefficients, _ = _fit(x, y * scale)
        perturb.append(_rmse(y, perturbed_coefficients[0] + perturbed_coefficients[1] * x))
    uncertainty = {
        "status": "PASS",
        "bootstrap_rmse_ci95": [float(np.percentile(bootstrap, 2.5)), float(np.percentile(bootstrap, 97.5))],
        "parameter_perturbation_range": [float(min(perturb)), float(max(perturb))],
        "model_uncertainty": {"alternative": "without_intercept", "rmse_difference": ablation["without_intercept_rmse"] - ablation["full_rmse"]},
    }
    output = {"schema": SCHEMA, "model": model, "theory": theory, "results": results, "ablation": ablation, "uncertainty": uncertainty}
    (destination / "reference_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    result = run_reference_pipeline(make_reference_data(), Path("reference-output"))
    print(json.dumps(result["results"], ensure_ascii=False, indent=2))

