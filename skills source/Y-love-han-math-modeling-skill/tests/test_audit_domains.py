"""M12: the audit command is a read-only, domain-separated audit."""

from __future__ import annotations

from helpers import build_through

from scripts.mmflow_core.audit import run_domain_audit
from scripts.mmflow_core.bindings import scan_unbound_numbers


def test_audit_domains_all_pass_on_completed_project(completed_project):
    report = run_domain_audit(completed_project)
    assert report["status"] == "PASS", report
    assert set(report["domains"]) == {
        "integrity",
        "lineage",
        "evidence",
        "scientific-bindings",
        "publication",
        "compliance",
        "review",
        "delivery",
        "release-status",
    }
    for domain, outcome in report["domains"].items():
        assert outcome["status"] in {"PASS", "NOT_APPLICABLE"}, (
            domain,
            outcome,
        )


def test_audit_domains_are_not_applicable_before_their_evidence(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    report = run_domain_audit(runtime)
    assert report["domains"]["publication"]["status"] == "NOT_APPLICABLE"
    assert report["domains"]["compliance"]["status"] == "PASS"
    assert report["domains"]["delivery"]["status"] == "NOT_APPLICABLE"


def test_audit_detects_result_source_drift(completed_project):
    runtime = completed_project
    # Corrupt the result artifact FILE that res_main actually binds (not the
    # registry record): the registry still loads, but scientific-bindings and
    # the publication closure must fail closed.
    result = runtime.registry.latest("result", "res_main")["payload"]
    bound_artifact = runtime.registry.latest("artifact", result["artifact_id"])[
        "payload"
    ]
    path = runtime.project_root / bound_artifact["relative_path"]
    path.write_bytes(path.read_bytes() + b"X")
    report = run_domain_audit(runtime)
    assert report["domains"]["scientific-bindings"]["status"] == "FAIL"
    # The tamper also breaks the publication closure (re-rendering the
    # manuscript reads the corrupted result), so the aggregate must fail
    # closed overall; no domain may hide the corruption as PASS.
    assert report["status"] in {"FAIL", "ERROR"}
    assert all(
        domain["status"] != "PASS"
        for name, domain in report["domains"].items()
        if name in {"scientific-bindings", "publication"}
    )


def test_audit_does_not_mutate(completed_project):
    runtime = completed_project
    before = runtime.ledger.head()["sequence"]
    run_domain_audit(runtime)
    assert runtime.ledger.head()["sequence"] == before
    assert not (runtime.project_root / ".mmflow/registry-journal.json").exists()
