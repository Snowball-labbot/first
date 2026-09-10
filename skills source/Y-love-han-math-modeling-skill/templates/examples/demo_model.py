from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    output_root = os.environ.get("MMFLOW_OUTPUT_DIR")
    if not output_root:
        raise SystemExit("This demo must still run in an isolated demo execution.")
    payload = {
        "schema": "mmflow-demo/v1",
        "artifact_class": "demo",
        "production_eligible": False,
        "message": "Demonstration only; contains no competition result.",
    }
    output = Path(output_root) / "demo-output.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n", "utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
