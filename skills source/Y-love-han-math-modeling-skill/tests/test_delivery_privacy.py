"""C15/C16/C17: archive paths, safe extraction, byte lock and privacy scans."""

from __future__ import annotations

import json
import zipfile

import pytest

from helpers import write_file

from scripts.mmflow_core.audit import create_delivery_archive, _verify_fresh_extraction
from scripts.mmflow_core.canonical import sha256_file
from scripts.mmflow_core.errors import IntegrityError
from scripts.mmflow_core.privacy import scan_file, scan_manifest_files


def _delivery_files(runtime) -> list[dict]:
    files = []
    seen: set[str] = set()
    for record in runtime.registry.iter_latest("artifact"):
        payload = record["payload"]
        logical = payload.get("logical_output_path")
        if logical in {"main.tex", "result.json"} and logical not in seen:
            seen.add(logical)
            files.append(
                {
                    "path": payload["relative_path"],
                    "sha256": payload["sha256"],
                    "artifact_id": payload["artifact_id"],
                }
            )
    return files


def _manifest(runtime, with_archive_paths: bool = True) -> dict:
    files = _delivery_files(runtime)
    if with_archive_paths:
        names = {"main.tex": "paper/main.tex", "result.json": "results/result.json"}
        for item in files:
            item["archive_path"] = names[item["path"].rsplit("/", 1)[-1]]
    return {"files": files, "excluded_prefixes": [".mmflow/"]}


def _write_manifest(runtime, manifest: dict):
    return write_file(
        runtime.project_root, "configs/delivery-manifest.json", json.dumps(manifest)
    )


def test_package_uses_archive_paths(p11_project):
    runtime = p11_project
    manifest = _manifest(runtime)
    path = _write_manifest(runtime, manifest)
    report = create_delivery_archive(
        runtime, path, "deliverables/candidate2.zip", candidate=True
    )
    with zipfile.ZipFile(runtime.project_root / report["package_path"], "r") as archive:
        names = archive.namelist()
    assert "paper/main.tex" in names
    assert "results/result.json" in names
    assert report["fresh_extract_test"] == "PASS"


def test_package_rejects_unsafe_archive_path(p11_project):
    runtime = p11_project
    manifest = _manifest(runtime)
    manifest["files"][0]["archive_path"] = "../escape.tex"
    path = _write_manifest(runtime, manifest)
    with pytest.raises(IntegrityError):
        create_delivery_archive(
            runtime, path, "deliverables/candidate3.zip", candidate=True
        )


def test_final_package_must_match_candidate_bytes(completed_project):
    runtime = completed_project
    manifest = _manifest(runtime)
    path = _write_manifest(runtime, manifest)
    # The shared completed project already contains the gated candidate
    # package; the final export must reproduce its bytes exactly.
    final = create_delivery_archive(
        runtime, path, "deliverables/final.zip", candidate=False
    )
    candidate_artifacts = [
        record["payload"]
        for record in runtime.registry.iter_latest("artifact")
        if record["payload"].get("artifact_type") == "delivery_package"
        and record["payload"].get("candidate") is True
    ]
    assert len(candidate_artifacts) == 1
    assert final["sha256"] == candidate_artifacts[0]["sha256"]
    # Change a delivered file -> final package must be rejected.
    source = runtime.project_root / manifest["files"][0]["path"]
    source.write_bytes(source.read_bytes() + b"X")
    with pytest.raises(IntegrityError):
        create_delivery_archive(
            runtime, path, "deliverables/final2.zip", candidate=False
        )


def test_fresh_extraction_rejects_zip_slip(completed_project):
    runtime = completed_project
    malicious = runtime.project_root / "deliverables/malicious.zip"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../evil.txt", b"pwned")
    with pytest.raises(IntegrityError):
        _verify_fresh_extraction(
            runtime,
            malicious,
            [("../evil.txt", malicious)],
        )


def test_privacy_scan_detects_secrets(completed_project):
    runtime = completed_project
    secret_file = write_file(
        runtime.project_root,
        "deliverables/leak.py",
        "api_key = 'sk-abcdefghijklmnopqrstuvwxyz1234'\n",
    )
    scanned = scan_file(secret_file, "deliverables/leak.py")
    assert any(
        finding["rule_id"] == "openai_api_key"
        and finding["severity"] == "CRITICAL"
        for finding in scanned["findings"]
    )


def test_privacy_scan_detects_absolute_paths(completed_project):
    runtime = completed_project
    leak_file = write_file(
        runtime.project_root,
        "deliverables/leak.txt",
        "本机路径 C:\\Users\\someone\\secret 与 /Users/someone/secret 泄露\n",
    )
    scanned = scan_file(leak_file, "deliverables/leak.txt")
    assert any(
        finding["rule_id"] == "absolute_path_leak" for finding in scanned["findings"]
    )


def test_privacy_scan_detects_pdf_metadata(completed_project):
    runtime = completed_project
    pdf_file = write_file(
        runtime.project_root,
        "deliverables/meta.pdf",
        b"%PDF-1.4\n1 0 obj<</Type /Catalog /Author (Alice) /Creator (TeX)>>endobj\n%%EOF",
    )
    scanned = scan_file(pdf_file, "deliverables/meta.pdf")
    assert any(
        finding["rule_id"] == "pdf_metadata" for finding in scanned["findings"]
    )


def test_privacy_scan_status_fail_on_hard_findings(completed_project):
    runtime = completed_project
    items = _delivery_files(runtime)
    write_file(
        runtime.project_root,
        "deliverables/secret.txt",
        "token: 3f2a1b9c7d4e8f0a6b5c4d3e2f1a0b9c8d7e6f5a\n",
    )
    secret = {
        "path": "deliverables/secret.txt",
        "sha256": sha256_file(runtime.project_root / "deliverables/secret.txt"),
    }
    report = scan_manifest_files(runtime, [*items, secret])
    assert report["status"] == "FAIL"
    assert any(
        finding["rule_id"] == "generic_secret_assignment"
        for file in report["files"]
        for finding in file["findings"]
    )
