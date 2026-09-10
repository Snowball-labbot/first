from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "integrate_templates", ROOT / "scripts" / "integrate_templates.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_manifest_contains_all_template_categories_and_safe_paths():
    manifest = MODULE.load_manifest(ROOT)

    assert manifest["schema"] == "math-modeling-template-manifest/v1"
    entries = manifest["templates"]
    assert entries
    assert {entry["category"] for entry in entries} >= {
        "analytics",
        "publication",
        "presentation",
        "quality",
        "production",
    }
    assert len({entry["id"] for entry in entries}) == len(entries)
    assert all(not Path(entry["path"]).is_absolute() for entry in entries)
    assert all(".." not in Path(entry["path"]).parts for entry in entries)


def test_manifest_rejects_duplicate_ids_and_unsafe_paths(tmp_path: Path):
    manifest = {
        "schema": "math-modeling-template-manifest/v1",
        "version": 1,
        "templates": [
            {"id": "one", "category": "analytics", "path": "../outside.py"},
            {"id": "one", "category": "analytics", "path": "ok.py"},
        ],
    }

    errors = MODULE.validate_manifest(tmp_path, manifest)

    assert any("duplicate template id" in error for error in errors)
    assert any("unsafe template path" in error for error in errors)


def test_resolve_template_rejects_unknown_and_unlisted_paths():
    manifest = {
        "schema": "math-modeling-template-manifest/v1",
        "version": 1,
        "templates": [
            {"id": "known", "category": "analytics", "path": "templates/a.py"}
        ],
    }

    with pytest.raises(MODULE.TemplateManifestError, match="unknown template id"):
        MODULE.resolve_template(ROOT, manifest, "missing")


def test_non_production_templates_cannot_be_declared_as_evidence():
    manifest = {
        "schema": "math-modeling-template-manifest/v1",
        "version": 1,
        "templates": [
            {
                "id": "analytics.bad",
                "category": "analytics",
                "path": "templates/a.py",
                "production_eligible": True,
                "evidence_types": ["structured_results"],
            }
        ],
    }

    errors = MODULE.validate_manifest(ROOT, manifest)

    assert any("non-production template cannot be evidence" in error for error in errors)
