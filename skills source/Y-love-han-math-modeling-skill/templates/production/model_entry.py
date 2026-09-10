from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any


REQUIRED_RESULT_FIELDS = (
    "metric",
    "value",
    "unit",
    "direction",
    "scenario",
    "dataset_split_id",
    "sample_size",
)


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_solver(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"implementation file is missing: {path}")
    spec = importlib.util.spec_from_file_location("mmflow_project_solver", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load implementation module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    solve = getattr(module, "solve", None)
    if not callable(solve):
        raise TypeError("implementation must export solve(input_data, config)")
    return solve


def validate_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != "mmflow-result-contract/v1":
        raise ValueError("solver must return mmflow-result-contract/v1")
    results = value.get("results")
    if not isinstance(results, dict) or not results:
        raise ValueError("production result contract must contain at least one result")
    for result_id, result in results.items():
        if not isinstance(result_id, str) or not result_id or not isinstance(result, dict):
            raise ValueError("invalid result entry")
        missing = [field for field in REQUIRED_RESULT_FIELDS if field not in result]
        if missing:
            raise ValueError(f"result {result_id} is missing: {', '.join(missing)}")
        number = result["value"]
        if (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not math.isfinite(float(number))
        ):
            raise ValueError(f"result {result_id} value must be finite")
        if not isinstance(result["sample_size"], int) or result["sample_size"] <= 0:
            raise ValueError(f"result {result_id} sample_size must be positive")
        for field in ("metric", "unit", "direction", "scenario", "dataset_split_id"):
            if not isinstance(result[field], str) or not result[field]:
                raise ValueError(f"result {result_id} requires non-empty {field}")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                value,
                handle,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an explicit project solver and emit a structured result contract."
    )
    parser.add_argument("--implementation", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-name", default="result-contract.json")
    args = parser.parse_args()
    output_root = os.environ.get("MMFLOW_OUTPUT_DIR")
    if not output_root:
        parser.error("MMFLOW_OUTPUT_DIR is required; run through mmflow")
    implementation = Path(args.implementation).resolve(strict=True)
    input_path = Path(args.input).resolve(strict=True)
    config_path = Path(args.config).resolve(strict=True)
    solve = load_solver(implementation)
    contract = validate_contract(solve(read_object(input_path), read_object(config_path)))
    output = Path(output_root).resolve() / args.output_name
    atomic_json(output, contract)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
