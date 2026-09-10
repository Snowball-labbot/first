"""C12: the recursive LaTeX publication execution closure."""

from __future__ import annotations

from helpers import advance, begin, build_through, gate, p7_evidence, p8_publication

import json


def _runtime_p7(tmp_path):
    runtime, _ = build_through(tmp_path, "P6")
    report = gate(runtime, "P6")
    assert report["status"] == "PASS"
    advance(runtime, "P6")
    begin(runtime, "P7")
    p7_evidence(runtime)
    report = gate(runtime, "P7")
    assert report["status"] == "PASS"
    advance(runtime, "P7")
    return runtime


def test_p8_publication_closure_passes(tmp_path):
    runtime = _runtime_p7(tmp_path)
    begin(runtime, "P8")
    p8_publication(runtime)
    report = gate(runtime, "P8")
    assert report["status"] == "PASS", report


def test_replacing_included_source_breaks_closure(tmp_path):
    runtime = _runtime_p7(tmp_path)
    begin(runtime, "P8")
    p8_publication(runtime)
    # Swap the included .tex content AFTER the closure was declared.
    (runtime.project_root / "manuscript/sections/s1.tex").write_text(
        "替换后的内容，哈希不再一致。\n", encoding="utf-8"
    )
    report = gate(runtime, "P8")
    assert report["status"] == "FAIL"


def test_legacy_v1_manifest_rejected_for_final_publication(tmp_path):
    runtime = _runtime_p7(tmp_path)
    begin(runtime, "P8")
    p8_publication(runtime)
    # Rewrite the emitted manifest artifact as a legacy v1 manifest.
    manifest_path = None
    for record in runtime.registry.iter_latest("artifact"):
        if record["payload"].get("logical_output_path") == "main.bindings.json":
            manifest_path = runtime.project_root / record["payload"]["relative_path"]
            break
    assert manifest_path is not None
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["binding_manifest_version"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = gate(runtime, "P8")
    assert report["status"] == "FAIL"
    assert "manifest v2" in report["checks"][0]["reason"] or any(
        "manifest v2" in check.get("reason", "")
        for check in report["checks"]
    )


def test_foreign_rendered_manuscript_rejected(tmp_path):
    runtime = _runtime_p7(tmp_path)
    begin(runtime, "P8")
    p8_publication(runtime, foreign_rendered=True)
    report = gate(runtime, "P8")
    assert report["status"] == "FAIL"
    reasons = " ".join(str(check.get("reason", "")) for check in report["checks"])
    assert "publication execution" in reasons or "controlled compile" in reasons
