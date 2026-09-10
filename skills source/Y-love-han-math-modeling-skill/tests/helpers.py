"""Shared fixture builder: a complete, honest P0 -> P11 -> COMPLETE project.

Every evidence payload here is built through the same program functions the
gate audits recompute, so the integration fixture verifies the whole chain
end to end instead of hand-crafting passing content.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scripts.mmflow_core.audit import create_delivery_archive
from scripts.mmflow_core.canonical import sha256_file
from scripts.mmflow_core.compliance import evaluate_requirements
from scripts.mmflow_core.privacy import scan_manifest_files
from scripts.mmflow_core.project import initialize_project, load_runtime, next_stage
from scripts.mmflow_core.runner import ExecutionRequest, ExecutionRunner

SKILL_ROOT = Path(__file__).resolve().parents[1]

P10_ROLES = [
    "competition_judge",
    "mathematics_numerics",
    "data_statistics",
    "reproducibility",
    "paper_compliance",
]

DIMENSIONS = [
    ("problem_response_formalization", 12.0, "problem_contract"),
    ("model_correctness", 18.0, "structured_results"),
    ("data_external_evidence", 12.0, "data_quality_report"),
    ("computation_numerics", 12.0, "validation_adapter_report"),
    ("validation_counterevidence", 18.0, "counterevidence_report"),
    ("contribution_decision_value", 12.0, "claim_registry"),
    ("reproducibility_traceability", 8.0, "reproduction_report"),
    ("paper_visual_communication", 8.0, "figure_registry"),
]


def make_runtime(tmp_path: Path, skill_root: Path = SKILL_ROOT):
    root = tmp_path / "project"
    runtime = initialize_project(root, "CUMCM", "2026A", skill_root=skill_root)
    return runtime


def reg(runtime, kind: str, payload: dict, stage: str | None = None) -> dict:
    payload = {**payload, "run_id": runtime.run_id}
    return runtime.registry.register(kind, payload, stage=stage)


def active(runtime) -> str | None:
    return runtime.workflow.state()["active_stage"]


def begin(runtime, stage: str) -> None:
    runtime.workflow.begin(stage)


def gate(runtime, stage: str) -> dict:
    """Run the exact gate path the CLI uses."""
    from scripts.mmflow_core.audit import semantic_stage_check
    from scripts.mmflow_core.gates import GateEngine
    from scripts.mmflow_core.project import load_policy

    state = runtime.workflow.state()
    assert state["active_stage"] == stage
    policy = load_policy(runtime, "evidence-v1.json")
    definition = policy["stage_requirements"][stage]
    active_redlines = sorted(
        {
            finding["payload"]["redline_id"]
            for finding in runtime.registry.iter_latest("finding")
            if finding["payload"].get("status") == "VALID"
            and finding["payload"].get("finding_status") == "OPEN"
            and finding["payload"].get("redline_id") in policy["redlines"]
        }
    )
    engine = GateEngine(
        runtime.project_root, runtime.registry, policy_version=policy["policy_id"]
    )
    report = engine.run(
        stage,
        {
            "required_evidence": definition["evidence_types"],
            "custom_checks": [
                (
                    definition["semantic_check"],
                    lambda _context: semantic_stage_check(runtime, stage),
                )
            ],
            "active_redlines": active_redlines,
            "current_stage": stage,
            "stage_epoch": state["stage_epochs"].get(stage),
            "stages_state": state["stages"],
            "cross_stage": policy.get("cross_stage_evidence", {}),
        },
        write_report=True,
    )
    if report["status"] == "BLOCKED":
        block_payload = None
        for check in report["checks"]:
            if isinstance(check.get("block"), dict):
                block_payload = dict(check["block"])
                block_payload.setdefault("reason", check.get("reason", ""))
                break
        if block_payload is None:
            raise AssertionError("BLOCKED gate lacks a structured block payload")
        runtime.workflow.block(stage, block_payload)
    else:
        runtime.workflow.record_gate(
            stage, report, report["evidence_fingerprint"]
        )
    return report


def advance(runtime, stage: str) -> None:
    from scripts.mmflow_core.gates import evidence_fingerprint
    from scripts.mmflow_core.project import load_policy

    policy = load_policy(runtime, "evidence-v1.json")
    runtime.workflow.advance(
        evidence_fingerprint(runtime.registry, stage, policy["policy_id"])
    )


def run_production(
    runtime,
    stage: str,
    question: str,
    role: str,
    *,
    code_files: list[str],
    input_files: list[str],
    config_files: list[str],
    source_artifact_ids: list[str],
    expected_outputs: list[str],
    comparison_policies: dict,
    dataset_split_ids: list[str] | None = None,
    timeout_seconds: int = 120,
    environment: dict | None = None,
    program: str = "code/model.py",
):
    request = ExecutionRequest(
        stage=stage,
        question=question,
        role=role,
        artifact_class="production",
        command=[sys.executable, program],
        input_paths=input_files,
        code_paths=code_files,
        config_paths=config_files,
        source_artifact_ids=source_artifact_ids,
        expected_outputs=expected_outputs,
        comparison_policies=comparison_policies,
        dataset_split_ids=dataset_split_ids or ["split_all"],
        random_protocol={},
        timeout_seconds=timeout_seconds,
        environment=environment or {},
    )
    return ExecutionRunner(
        runtime.project_root, runtime.ledger, runtime.registry, runtime.run_id
    ).execute(request)


def write_file(root: Path, relative: str, content: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="\n")
    return path


def register_external(
    runtime, artifact_id: str, relative: str, artifact_type: str, stage: str
) -> dict:
    path = runtime.project_root / relative
    return reg(
        runtime,
        "artifact",
        {
            "artifact_id": artifact_id,
            "artifact_class": "external",
            "artifact_type": artifact_type,
            "status": "VALID",
            "relative_path": relative,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "inputs": [],
        },
        stage=stage,
    )


# --------------------------------------------------------------------------
# Stage evidence builders
# --------------------------------------------------------------------------

def p0_evidence(runtime, *, requirements: list | None = None) -> None:
    root = runtime.project_root
    if requirements is None:
        requirements = [
            {
                "requirement_id": "pdf_required",
                "kind": "boolean",
                "value": False,
                "scope": "paper",
                "severity": "HARD",
                "source_citation_id": "cite_rule",
                "snapshot_artifact_id": "art_rule",
                "source_locator": {"type": "page_clause", "page": 1, "clause": "1.1"},
                "verification_method": "artifact_presence",
            }
        ]
    rules_path = write_file(
        root,
        "inputs/rules.pdf",
        b"%PDF-1.4\n1 0 obj<</Type /Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF",
    )
    problem_path = write_file(root, "inputs/problem.txt", "2026 年赛题正文。\n")
    art_rule = register_external(
        runtime, "art_rule", "inputs/rules.pdf", "official_rule_snapshot", "P0"
    )
    register_external(runtime, "art_problem", "inputs/problem.txt", "problem_statement", "P0")
    reg(
        runtime,
        "citation",
        {
            "citation_id": "cite_rule",
            "title": "官方参赛规则 2026",
            "authors": ["赛事主办方"],
            "year": "2026",
            "source_url": "https://example.org/rules/2026",
            "access_level": "public",
            "verified_at": "2026-08-01T00:00:00+00:00",
            "verification_status": "verified",
            "source_role": "official_rule",
            "version": "2026",
            "metadata_verification": {
                "method": "direct_download",
                "checks": ["url_reachable", "document_present"],
            },
            "source_locator": {"type": "page_clause", "page": 1, "clause": "1.1"},
            "content_support_verification": "规则正文核验",
            "supports_claims": [],
            "display_value": "2026",
            "status": "VALID",
        },
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_capability",
            "evidence_type": "capability_report",
            "status": "VALID",
            "content": {
                "checked_at": "2026-08-05T00:00:00+00:00",
                "capabilities": {"python": True, "filesystem": True, "network": "not_probed"},
                "limitations": ["no_os_sandbox"],
            },
            "supports": [],
        },
        stage="P0",
    )
    digest = sha256_file(rules_path)
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_rules",
            "evidence_type": "competition_rules",
            "status": "VALID",
            "content": {
                "competition": "CUMCM",
                "edition": "2026A",
                "official_sources": [
                    {
                        "artifact_id": "art_rule",
                        "citation_id": "cite_rule",
                        "source_url": "https://example.org/rules/2026",
                        "retrieved_at": "2026-08-01T00:00:00+00:00",
                        "version": "2026",
                    }
                ],
                "rule_snapshots": [
                    {
                        "artifact_id": "art_rule",
                        "citation_id": "cite_rule",
                        "sha256": digest,
                        "competition": "CUMCM",
                        "edition": "2026A",
                    }
                ],
                "requirements": requirements,
                "verification_status": "verified",
            },
            "supports": ["art_rule", "cite_rule"],
        },
        stage="P0",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_lock",
            "evidence_type": "policy_lock",
            "status": "VALID",
            "content": {
                "policy_sha256": runtime.policy_lock["policy_sha256"],
                "files": runtime.policy_lock["files"],
            },
            "supports": [],
        },
        stage="P0",
    )


def p1_evidence(runtime) -> None:
    problem_artifact = runtime.registry.latest("artifact", "art_problem")["payload"]
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_inventory",
            "evidence_type": "input_inventory",
            "status": "VALID",
            "content": {
                "files": [
                    {
                        "artifact_id": "art_problem",
                        "sha256": problem_artifact["sha256"],
                        "read_status": "complete",
                    }
                ],
                "critical_missing": False,
            },
            "supports": ["art_problem"],
        },
        stage="P1",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_selection",
            "evidence_type": "selection_record",
            "status": "VALID",
            "content": {
                "applicable": False,
                "candidates": [],
                "selected": None,
                "rationale": "单题赛事，无需选题",
            },
            "supports": [],
        },
        stage="P1",
    )


def p2_evidence(runtime) -> None:
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_matrix",
            "evidence_type": "requirement_matrix",
            "status": "VALID",
            "content": {
                "requirements": [
                    {
                        "requirement_id": "req_1",
                        "source_anchor": "problem.pdf 第2页 问题1",
                        "response_target": "正文 第3节",
                    }
                ]
            },
            "supports": [],
        },
        stage="P2",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_contract",
            "evidence_type": "problem_contract",
            "status": "VALID",
            "content": {
                "problems": [
                    {
                        "problem_id": "prob_a",
                        "traits": ["constrained"],
                        "claim_types": ["scenario"],
                        "model_families": [],
                        "properties": {},
                    }
                ]
            },
            "supports": [],
        },
        stage="P2",
    )


def p3_evidence(runtime, *, literature_ids: list | None = None) -> None:
    # M07: dataset splits are first-class immutable entities.
    if literature_ids is None:
        literature_ids = []
    problem_artifact = runtime.registry.latest("artifact", "art_problem")["payload"]
    reg(
        runtime,
        "split",
        {
            "split_id": "split_all",
            "source_dataset_artifact_id": "art_problem",
            "split_kind": "random",
            "selectors": {"seed": 42, "ratio": 1.0},
            "indices_sha256": problem_artifact["sha256"],
            "leakage_boundary": {"preprocessing": "none"},
            "preprocessing_fit_scope": "train_only",
            "immutable_fingerprint": problem_artifact["sha256"],
            "status": "VALID",
        },
        stage="P3",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_lineage",
            "evidence_type": "data_lineage",
            "status": "VALID",
            "content": {
                "sources": [{"artifact_id": "art_problem"}],
                "transforms": [],
                "splits": ["split_all"],
            },
            "supports": ["art_problem", "split_all"],
        },
        stage="P3",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_data_quality",
            "evidence_type": "data_quality_report",
            "status": "VALID",
            "content": {
                "datasets": [{"artifact_id": "art_problem"}],
                "issues": [],
                "decisions": [],
            },
            "supports": ["art_problem"],
        },
        stage="P3",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_literature",
            "evidence_type": "literature_registry",
            "status": "VALID",
            "content": {"citation_ids": literature_ids, "unresolved": False},
            "supports": list(literature_ids),
        },
        stage="P3",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_leakage",
            "evidence_type": "leakage_audit",
            "status": "VALID",
            "content": {
                "checks": [{"id": "split_audit", "status": "PASS"}],
                "status": "PASS",
            },
            "supports": [],
        },
        stage="P3",
    )


def p4_evidence(runtime) -> None:
    comparison_policies = {
        "result.json": {
            "mode": "json_numeric",
            "absolute_tolerance": 0.001,
            "relative_tolerance": 0.001,
        }
    }
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_baseline",
            "evidence_type": "baseline_protocol",
            "status": "VALID",
            "content": {"baselines": ["baseline_linear"], "metrics": ["rmse"]},
            "supports": [],
        },
        stage="P4",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_candidates",
            "evidence_type": "model_candidates",
            "status": "VALID",
            "content": {"candidates": ["model_main"], "selection_rule": "best_validated"},
            "supports": [],
        },
        stage="P4",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_validation",
            "evidence_type": "validation_protocol",
            "status": "VALID",
            "content": {
                "adapters": [
                    "constraint_feasibility",
                    "program_and_model_validation",
                    "uncertainty_scope",
                ],
                "metrics": ["rmse"],
                "stopping_rules": [],
                "comparison_policies": comparison_policies,
                "environment_drift_policy": {"allowed_differences": []},
            },
            "supports": [],
        },
        stage="P4",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_frozen",
            "evidence_type": "frozen_analysis_plan",
            "status": "VALID",
            "content": {
                "frozen_at": "2026-08-05T00:00:00+00:00",
                "viewed_final_test": False,
                "primary_metrics": ["rmse"],
                "split_ids": ["split_all"],
            },
            "supports": ["split_all"],
        },
        stage="P4",
    )
    return comparison_policies


def p5_execution(runtime, comparison_policies: dict) -> tuple[str, dict, str]:
    root = runtime.project_root
    write_file(
        root,
        "code/model.py",
        (
            "import json, os\n"
            "out = os.environ['MMFLOW_OUTPUT_DIR']\n"
            "with open(os.path.join(out, 'result.json'), 'w', encoding='utf-8') as f:\n"
            "    json.dump({\n"
            "        'schema': 'mmflow-result-contract/v1',\n"
            "        'results': {\n"
            "            'main': {\n"
            "                'metric': 'rmse', 'unit': 'unit',\n"
            "                'direction': 'lower_is_better',\n"
            "                'scenario': 'default',\n"
            "                'dataset_split_id': 'split_all',\n"
            "                'sample_size': 100,\n"
            "                'value': 3.14,\n"
            "            }\n"
            "        }\n"
            "    }, f)\n"
        ),
    )
    write_file(
        root,
        "configs/run_p5.json",
        json.dumps(
            {
                "input_paths": ["inputs/problem.txt"],
                "code_paths": ["code/model.py"],
                "config_paths": [],
                "source_artifact_ids": ["art_problem", "art_model"],
                "expected_outputs": ["result.json"],
                "comparison_policies": comparison_policies,
            }
        ),
    )
    register_external(runtime, "art_model", "code/model.py", "source_code", "P5")
    result = run_production(
        runtime,
        "P5",
        "q1",
        "model_main",
        code_files=["code/model.py"],
        input_files=["inputs/problem.txt"],
        config_files=[],
        source_artifact_ids=["art_problem", "art_model"],
        expected_outputs=["result.json"],
        comparison_policies=comparison_policies,
    )
    execution_id = result.execution["payload"]["execution_id"]
    artifact = next(
        item["payload"]
        for item in result.artifacts
        if item["payload"].get("logical_output_path") == "result.json"
    )
    reg(
        runtime,
        "result",
        {
            "result_id": "res_main",
            "artifact_id": artifact["artifact_id"],
            "execution_id": execution_id,
            "status": "VALID",
            "question_id": "q1",
            "model_id": "model_main",
            "result_kind": "scalar",
            "metric": "rmse",
            "value": 3.14,
            "unit": "unit",
            "direction": "lower_is_better",
            "scenario": "default",
            "dataset_split_id": "split_all",
            "sample_size": 100,
            "source_locator": {"format": "json_pointer", "pointer": "/results/main"},
            "display": {"rounding": "half_even", "decimals": 2, "rendered": "3.14"},
        },
        stage="P5",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_prod_exec",
            "evidence_type": "production_execution",
            "status": "VALID",
            "content": {"execution_ids": [execution_id]},
            "supports": [execution_id],
        },
        stage="P5",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_results",
            "evidence_type": "structured_results",
            "status": "VALID",
            "content": {"result_ids": ["res_main"]},
            "supports": ["res_main"],
        },
        stage="P5",
    )
    return execution_id, artifact, "res_main"


def p6_evidence(runtime) -> None:
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_adapter",
            "evidence_type": "validation_adapter_report",
            "status": "VALID",
            "content": {
                "reports": [
                    {
                        "problem_id": "prob_a",
                        "completed": {
                            "constraint_feasibility": "PASS",
                            "program_and_model_validation": "PASS",
                            "uncertainty_scope": "PASS",
                        },
                        "waivers": {},
                    }
                ]
            },
            "supports": [],
        },
        stage="P6",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_degenerate",
            "evidence_type": "degenerate_test",
            "status": "VALID",
            "content": {
                "tests": [{"id": "d1", "status": "PASS"}],
                "status": "PASS",
            },
            "supports": [],
        },
        stage="P6",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_counter",
            "evidence_type": "counterevidence_report",
            "status": "VALID",
            "content": {"tests": [], "unsupported_claims": [], "status": "PASS"},
            "supports": [],
        },
        stage="P6",
    )


def p7_evidence(runtime) -> None:
    reg(
        runtime,
        "claim",
        {
            "claim_id": "claim_main",
            "claim_type": "computed",
            "statement": "主模型RMSE为3.14",
            "status": "VALID",
            "supports": ["res_main"],
            "counterevidence": [],
            "scope": "给定数据集",
            "strength": "confirmed",
        },
        stage="P7",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_response",
            "evidence_type": "response_matrix",
            "status": "VALID",
            "content": {
                "rows": [
                    {
                        "requirement_id": "req_1",
                        "claim_ids": ["claim_main"],
                        "manuscript_target": "sec:main",
                    }
                ]
            },
            "supports": ["claim_main"],
        },
        stage="P7",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_claims",
            "evidence_type": "claim_registry",
            "status": "VALID",
            "content": {"claim_ids": ["claim_main"]},
            "supports": ["claim_main"],
        },
        stage="P7",
    )


def p8_publication(runtime, *, foreign_rendered: bool = False) -> dict:
    """Render bindings, run the controlled publication execution and register
    the P8 evidence.  ``foreign_rendered`` binds the rendered manuscript to a
    DIFFERENT execution than the declared publication execution (adversarial).
    """
    root = runtime.project_root
    write_file(
        root,
        "manuscript/main.tex",
        (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\section{结果}\n"
            "主模型RMSE为\\MMResult{res_main}，规则参见\\cite{cite_rule}。\n"
            "\\input{sections/s1}\n"
            "\\end{document}\n"
        ),
    )
    write_file(
        root,
        "manuscript/sections/s1.tex",
        "包含文件内容，无未绑定数字。\n",
    )
    from scripts.mmflow_core.bindings import render_project_latex_bindings

    render_project_latex_bindings(
        root / "manuscript/main.tex",
        runtime.registry,
        root,
        "manuscript/rendered/main.tex",
    )
    write_file(
        root,
        "code/emit.py",
        (
            "import os, shutil\n"
            "out = os.environ['MMFLOW_OUTPUT_DIR']\n"
            "shutil.copy2('manuscript/rendered/main.tex', os.path.join(out, 'main.tex'))\n"
            "os.makedirs(os.path.join(out, 'main.sources', 'sections'), exist_ok=True)\n"
            "shutil.copy2('manuscript/rendered/main.sources/sections/s1.tex',\n"
            "             os.path.join(out, 'main.sources', 'sections', 's1.tex'))\n"
            "shutil.copy2('manuscript/rendered/main.bindings.json',\n"
            "             os.path.join(out, 'main.bindings.json'))\n"
        ),
    )
    register_external(runtime, "art_main_tex", "manuscript/main.tex", "paper_source", "P8")
    register_external(
        runtime, "art_s1_tex", "manuscript/sections/s1.tex", "paper_source", "P8"
    )
    write_file(
        root,
        "configs/run_p8.json",
        json.dumps(
            {
                "input_paths": [
                    "manuscript/rendered/main.tex",
                    "manuscript/rendered/main.sources/sections/s1.tex",
                    "manuscript/rendered/main.bindings.json",
                ],
                "code_paths": ["code/emit.py"],
                "config_paths": [],
                "source_artifact_ids": ["art_emit", "art_r0", "art_r1", "art_r2"],
                "expected_outputs": [
                    "main.tex",
                    "main.sources/sections/s1.tex",
                    "main.bindings.json",
                ],
                "comparison_policies": {
                    "main.tex": {"mode": "sha256"},
                    "main.sources/sections/s1.tex": {"mode": "sha256"},
                    "main.bindings.json": {"mode": "sha256"},
                },
            }
        ),
    )
    register_external(runtime, "art_emit", "code/emit.py", "source_code", "P8")
    rendered_files = [
        "manuscript/rendered/main.tex",
        "manuscript/rendered/main.sources/sections/s1.tex",
        "manuscript/rendered/main.bindings.json",
    ]
    for index, relative in enumerate(rendered_files):
        register_external(
            runtime, f"art_r{index}", relative, "rendered_paper", "P8"
        )
    result = run_production(
        runtime,
        "P8",
        "q1",
        "publish",
        code_files=["code/emit.py"],
        input_files=rendered_files,
        config_files=[],
        source_artifact_ids=["art_emit", "art_r0", "art_r1", "art_r2"],
        expected_outputs=[
            "main.tex",
            "main.sources/sections/s1.tex",
            "main.bindings.json",
        ],
        comparison_policies={
            "main.tex": {"mode": "sha256"},
            "main.sources/sections/s1.tex": {"mode": "sha256"},
            "main.bindings.json": {"mode": "sha256"},
        },
        program="code/emit.py",
    )
    publication_execution_id = result.execution["payload"]["execution_id"]
    by_output = {
        item["payload"]["logical_output_path"]: item["payload"]
        for item in result.artifacts
    }
    if foreign_rendered:
        # Run the same compile again: the evidence then binds the rendered
        # manuscript to a different execution than the declared one.
        foreign = run_production(
            runtime,
            "P8",
            "q1",
            "publish",
            code_files=["code/emit.py"],
            input_files=rendered_files,
            config_files=[],
            source_artifact_ids=["art_emit", "art_r0", "art_r1", "art_r2"],
            expected_outputs=[
                "main.tex",
                "main.sources/sections/s1.tex",
                "main.bindings.json",
            ],
            comparison_policies={
                "main.tex": {"mode": "sha256"},
                "main.sources/sections/s1.tex": {"mode": "sha256"},
                "main.bindings.json": {"mode": "sha256"},
            },
            program="code/emit.py",
        )
        foreign_outputs = {
            item["payload"]["logical_output_path"]: item["payload"]
            for item in foreign.artifacts
        }
        by_output["main.tex"] = foreign_outputs["main.tex"]
    s1_tex = runtime.registry.latest("artifact", "art_s1_tex")["payload"]
    main_artifact = runtime.registry.latest("artifact", "art_main_tex")["payload"]
    source_closure = [
        {
            "path": "manuscript/main.tex",
            "sha256": main_artifact["sha256"],
            "artifact_id": "art_main_tex",
        },
        {
            "path": "manuscript/sections/s1.tex",
            "sha256": s1_tex["sha256"],
            "artifact_id": "art_s1_tex",
        },
    ]
    binding_manifest = json.loads(
        (root / "manuscript/rendered/main.bindings.json").read_text("utf-8")
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_manuscript",
            "evidence_type": "manuscript_source",
            "status": "VALID",
            "content": {
                "source_artifact_id": "art_main_tex",
                "rendered_artifact_id": by_output["main.tex"]["artifact_id"],
                "binding_manifest_artifact_id": by_output["main.bindings.json"][
                    "artifact_id"
                ],
                "source_closure": source_closure,
                "binding_count": binding_manifest["binding_count"],
                "unbound_number_count": 0,
                "publication_execution_id": publication_execution_id,
                "compile_dependencies": [],
            },
            "supports": [
                "art_main_tex",
                by_output["main.tex"]["artifact_id"],
                by_output["main.bindings.json"]["artifact_id"],
                "art_main_tex",
                "art_s1_tex",
            ],
        },
        stage="P8",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_figures",
            "evidence_type": "figure_registry",
            "status": "VALID",
            "content": {"figure_ids": []},
            "supports": [],
        },
        stage="P8",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_citations",
            "evidence_type": "citation_audit",
            "status": "VALID",
            "content": {"citation_ids": ["cite_rule"], "unresolved": False},
            "supports": ["cite_rule"],
        },
        stage="P8",
    )
    return {"publication_execution_id": publication_execution_id, "outputs": by_output}


def p9_reproduction(runtime, execution_id: str) -> dict:
    runner = ExecutionRunner(
        runtime.project_root, runtime.ledger, runtime.registry, runtime.run_id
    )
    reproduced = runner.reproduce(execution_id)
    report = runner.compare_reproduction(execution_id, reproduced)
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_repro",
            "evidence_type": "reproduction_report",
            "status": "VALID",
            "content": {"reports": [report]},
            "supports": [execution_id, reproduced.execution["payload"]["execution_id"]],
        },
        stage="P9",
    )
    return report


def p10_review(runtime, *, independent: bool = False) -> None:
    mode = "independent_agent" if independent else "same_agent_roleplay"
    independence = "independent" if independent else "limited"
    review_report_ids: list[str] = []
    roles: list[dict[str, Any]] = []
    for index, role in enumerate(P10_ROLES):
        evidence_id = f"ev_review_{role}"
        review_report_ids.append(evidence_id)
        reg(
            runtime,
            "evidence",
            {
                "evidence_id": evidence_id,
                "evidence_type": "review_report",
                "status": "VALID",
                "content": {
                    "role": role,
                    "scope": ["whole_submission"],
                    "checks": [{"check_id": f"{role}_c1", "status": "PASS"}],
                    "finding_ids": [],
                    "reviewer_mode": mode,
                },
                "supports": [],
            },
            stage="P10",
        )
        roles.append(
            {
                "role": role,
                "status": "COMPLETE",
                "evidence_ids": [evidence_id],
                "finding_ids": [],
            }
        )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_findings",
            "evidence_type": "review_findings",
            "status": "VALID",
            "content": {
                "finding_ids": [],
                "open_by_severity": {
                    "CRITICAL": 0,
                    "MAJOR": 0,
                    "MODERATE": 0,
                    "MINOR": 0,
                },
                "independent_review": independence,
                "roles": roles,
            },
            "supports": review_report_ids,
        },
        stage="P10",
    )
    rules_payload = runtime.registry.latest("evidence", "ev_rules")["payload"]
    requirement_checks = evaluate_requirements(
        runtime, rules_payload["content"].get("requirements")
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_compliance",
            "evidence_type": "compliance_report",
            "status": "VALID",
            "content": {
                "checks": [],
                "status": "PASS",
                "official_rule_citations": ["cite_rule"],
                "requirement_checks": requirement_checks,
            },
            "supports": ["cite_rule"],
        },
        stage="P10",
    )
    dimensions = []
    for index, (dimension_id, maximum, _evidence_type) in enumerate(DIMENSIONS):
        evidence_ids = _dimension_evidence_ids(index)
        dimensions.append(
            {
                "id": dimension_id,
                "maximum": maximum,
                "earned": maximum,
                "evidence_ids": evidence_ids,
            }
        )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_quality",
            "evidence_type": "quality_assessment",
            "status": "VALID",
            "content": {
                "dimensions": dimensions,
                "total": 100.0,
                "contribution_claim_ids": ["claim_main"],
                "review_independence": independence,
            },
            "supports": ["claim_main"],
        },
        stage="P10",
    )


def _dimension_evidence_ids(index: int) -> list[str]:
    mapping = [
        "ev_contract",
        "ev_results",
        "ev_data_quality",
        "ev_adapter",
        "ev_counter",
        "ev_claims",
        "ev_repro",
        "ev_figures",
    ]
    return [mapping[index]]


def p11_delivery(
    runtime,
    *,
    package: bool = True,
    extra_files: list[dict] | None = None,
    distribution_licenses: list[dict] | None = None,
) -> dict:
    """Build delivery manifest, scan privacy, package the candidate and
    register the P11 evidence.  ``package=False`` skips archive creation so
    tests can exercise the packaging command themselves."""
    root = runtime.project_root
    result_artifact = None
    for record in runtime.registry.iter_latest("artifact"):
        if record["payload"].get("logical_output_path") == "result.json":
            result_artifact = record["payload"]
            break
    assert result_artifact is not None
    main_artifact = None
    for record in runtime.registry.iter_latest("artifact"):
        if record["payload"].get("logical_output_path") == "main.tex":
            main_artifact = record["payload"]
            break
    assert main_artifact is not None
    files = [
        {
            "path": main_artifact["relative_path"],
            "sha256": main_artifact["sha256"],
            "artifact_id": main_artifact["artifact_id"],
            "archive_path": "paper/main.tex",
        },
        {
            "path": result_artifact["relative_path"],
            "sha256": result_artifact["sha256"],
            "artifact_id": result_artifact["artifact_id"],
            "archive_path": "results/result.json",
        },
    ]
    if extra_files:
        files = files + list(extra_files)
    delivery_manifest = {
        "files": files,
        "excluded_prefixes": [".mmflow/"],
        "distribution_licenses": distribution_licenses or [],
        "smoke_command": [
            sys.executable,
            "-c",
            (
                "import json, os, sys\n"
                "json.load(open(os.path.join('results', 'result.json'), encoding='utf-8'))\n"
                "print('smoke ok')\n"
            ),
        ],
    }
    write_file(root, "configs/delivery-manifest.json", json.dumps(delivery_manifest))
    privacy_report = scan_manifest_files(runtime, files)
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_manifest",
            "evidence_type": "delivery_manifest",
            "status": "VALID",
            "content": delivery_manifest,
            "supports": [str(item["artifact_id"]) for item in files],
        },
        stage="P11",
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_privacy",
            "evidence_type": "privacy_scan",
            "status": "VALID",
            "content": privacy_report,
            "supports": [],
        },
        stage="P11",
    )
    package_report = None
    if package:
        package_report = create_delivery_archive(
            runtime,
            "configs/delivery-manifest.json",
            "deliverables/candidate.zip",
            candidate=True,
        )
    if package_report is not None:
        reg(
            runtime,
            "evidence",
            {
                "evidence_id": "ev_checksum",
                "evidence_type": "package_checksum",
                "status": "VALID",
                "content": {
                    "package_artifact_id": package_report["package_artifact_id"],
                    "sha256": package_report["sha256"],
                    "archive_test": "PASS",
                },
                "supports": [package_report["package_artifact_id"]],
            },
            stage="P11",
        )
    return {
        "package_report": package_report,
        "privacy_report": privacy_report,
        "manifest_path": "configs/delivery-manifest.json",
        "files": files,
    }


def p10_minimal_without_reviews(runtime) -> None:
    """Register P10 required evidence (findings, compliance, quality) without
    any review_report evidence.

    This leaves ``_review_modes`` empty, which exercises the
    QUALITY_REVIEW_READY / REPRODUCIBLE label path in release.py.
    """
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_findings",
            "evidence_type": "review_findings",
            "status": "VALID",
            "content": {
                "finding_ids": [],
                "open_by_severity": {
                    "CRITICAL": 0,
                    "MAJOR": 0,
                    "MODERATE": 0,
                    "MINOR": 0,
                },
                "independent_review": "not_started",
                "roles": [],
            },
            "supports": [],
        },
        stage="P10",
    )
    rules_payload = runtime.registry.latest("evidence", "ev_rules")["payload"]
    requirement_checks = evaluate_requirements(
        runtime, rules_payload["content"].get("requirements")
    )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_compliance",
            "evidence_type": "compliance_report",
            "status": "VALID",
            "content": {
                "checks": [],
                "status": "PASS",
                "official_rule_citations": ["cite_rule"],
                "requirement_checks": requirement_checks,
            },
            "supports": ["cite_rule"],
        },
        stage="P10",
    )
    dimensions = []
    for index, (dimension_id, maximum, _evidence_type) in enumerate(DIMENSIONS):
        evidence_ids = _dimension_evidence_ids(index)
        dimensions.append(
            {
                "id": dimension_id,
                "maximum": maximum,
                "earned": maximum,
                "evidence_ids": evidence_ids,
            }
        )
    reg(
        runtime,
        "evidence",
        {
            "evidence_id": "ev_quality",
            "evidence_type": "quality_assessment",
            "status": "VALID",
            "content": {
                "dimensions": dimensions,
                "total": 100.0,
                "contribution_claim_ids": ["claim_main"],
                "review_independence": "not_started",
            },
            "supports": ["claim_main"],
        },
        stage="P10",
    )


STAGE_BUILDERS = {
    "P0": p0_evidence,
    "P1": p1_evidence,
    "P2": p2_evidence,
    "P3": p3_evidence,
    "P4": p4_evidence,
    "P5": p5_execution,
    "P6": p6_evidence,
    "P7": p7_evidence,
    "P8": p8_publication,
    "P9": p9_reproduction,
    "P10": p10_review,
    "P11": p11_delivery,
}


def build_through(
    tmp_path,
    upto: str,
    *,
    independent: bool = False,
    runtime: Any = None,
) -> tuple[Any, dict[str, Any]]:
    """Build P0 .. upto (inclusive) and leave the stage ACTIVE, un-gated.

    Returns (runtime, context) where context carries cross-stage values
    (comparison policies, execution id) for later builders.
    """
    if runtime is None:
        runtime = make_runtime(tmp_path)
    context: dict[str, Any] = {}
    for stage in [f"P{i}" for i in range(12)]:
        begin(runtime, stage)
        if stage == "P4":
            context["comparison_policies"] = p4_evidence(runtime)
        elif stage == "P5":
            execution_id, artifact, result_id = p5_execution(
                runtime, context["comparison_policies"]
            )
            context["execution_id"] = execution_id
            context["artifact"] = artifact
            context["result_id"] = result_id
        elif stage == "P9":
            p9_reproduction(runtime, context["execution_id"])
        elif stage == "P10":
            p10_review(runtime, independent=independent)
        else:
            STAGE_BUILDERS[stage](runtime)
        if stage == upto:
            return runtime, context
        report = gate(runtime, stage)
        assert report["status"] == "PASS", f"gate {stage} failed: {report}"
        advance(runtime, stage)
    raise AssertionError(f"unreachable upto={upto}")


def build_completed_project(
    tmp_path, *, independent: bool = False, runtime: Any = None
):
    """P0 -> P11 -> COMPLETE with the limited/independent review label."""
    runtime, _context = build_through(
        tmp_path, "P11", independent=independent, runtime=runtime
    )
    report = gate(runtime, "P11")
    assert report["status"] == "PASS", f"gate P11 failed: {report}"
    advance(runtime, "P11")
    state = runtime.workflow.state()
    assert state["complete"] is True
    return runtime
