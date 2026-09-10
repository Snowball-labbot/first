from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_integrated_skill_has_core_runtime_and_layered_templates():
    required = [
        ROOT / "SKILL.md",
        ROOT / "agents" / "openai.yaml",
        ROOT / "scripts" / "mmflow.py",
        ROOT / "scripts" / "validate_skill.py",
        ROOT / "scripts" / "mmflow_core",
        ROOT / "templates" / "production",
        ROOT / "templates" / "analytics",
        ROOT / "templates" / "publication",
        ROOT / "templates" / "presentation",
        ROOT / "templates" / "quality",
        ROOT / "templates" / "template_manifest.json",
    ]
    assert all(path.exists() for path in required)


def test_integrated_skill_name_and_manifest_version_are_final():
    frontmatter = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()[:5]
    assert "name: math-modeling" in frontmatter
    manifest = json.loads((ROOT / "templates" / "template_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "math-modeling-template-manifest/v1"
    assert len(manifest["templates"]) >= 20
    assert len({entry["id"] for entry in manifest["templates"]}) == len(manifest["templates"])


def test_no_python_cache_or_placeholder_is_delivered():
    files = [path for path in ROOT.rglob("*") if path.is_file()]
    generated = [path for path in files if path.suffix == ".pyc" or "__pycache__" in path.parts]
    assert not generated, f"generated cache files are not deliverable: {generated}"
    text_files = [path for path in files if path.suffix in {".md", ".py", ".json", ".yaml", ".tex"}]
    forbidden = tuple("[" + marker + ":" for marker in ("TODO", "TBD", "FIXME"))
    assert not any(token in path.read_text(encoding="utf-8", errors="ignore") for path in text_files for token in forbidden)


def test_skill_exposes_original_strengths_as_verifiable_integrated_routes():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    required_fragments = (
        "原版优势的可验证整合映射",
        "统一数学框架",
        "反直觉发现",
        "两轮自批判",
        "负面结果",
        "数学美学",
        "跨问题迁移",
        "CP1–CP6",
        "theorem_application_record",
        "innovation_ablation_record",
        "counterintuitive_finding_record",
        "cross_problem_framework_record",
        "mechanism_explanation_record",
        "negative_result_record",
        "paper_depth_review",
        "NOT_APPLICABLE",
        "固定页数、图数、算法数",
        "信息增量",
    )
    missing = [fragment for fragment in required_fragments if fragment not in text]
    assert not missing, f"original-strength mapping is incomplete: {missing}"
