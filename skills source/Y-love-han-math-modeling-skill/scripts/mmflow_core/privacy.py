from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from .errors import EvidenceInsufficientError, IntegrityError
from .project import Runtime

CHECKER_VERSION = "privacy-scanner/v1"

SECRET_PATTERNS: list[tuple[str, re.Pattern[bytes]]] = [
    ("openai_api_key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("aws_access_key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("private_key_block", re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("bearer_token", re.compile(rb"(?i)\bauthorization:\s*bearer\s+\S+")),
    ("generic_secret_assignment", re.compile(rb"(?i)\b(?:api[_-]?key|secret|password|token|passwd)\s*[:=]\s*['\"]?[A-Za-z0-9!@#$%^&*_.-]{8,}")),
]

ABSOLUTE_PATH_PATTERN = re.compile(
    rb"(?i)(?:[A-Za-z]:[\\/]|\\\\[A-Za-z0-9_.-]+\\|/Users/[A-Za-z0-9_.-]+|/home/[A-Za-z0-9_.-]+)"
)

FORBIDDEN_BASENAMES = {
    ".git",
    ".gitignore",
    ".DS_Store",
    ".vscode",
    ".idea",
    ".mmflow",
}
FORBIDDEN_SUFFIXES = {".swp", ".tmp", ".bak", "~"}

PDF_METADATA_KEYS = (b"/Author", b"/Creator", b"/Producer")
EXIF_MARKER = b"Exif\x00\x00"
EXIF_SOFTWARE = b"Software"
EXIF_GPS = b"GPS"

NESTED_ARCHIVE_SUFFIXES = (".zip", ".tar", ".gz", ".7z", ".rar")


def _scan_bytes(data: bytes, relative: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lower = relative.lower()
    for suffix in FORBIDDEN_SUFFIXES:
        if lower.endswith(suffix):
            findings.append(
                {
                    "rule_id": "forbidden_file_suffix",
                    "severity": "MAJOR",
                    "location": relative,
                    "detail": f"editor/temp suffix {suffix} must not be delivered",
                }
            )
    for name in FORBIDDEN_BASENAMES:
        if f"/{name}/" in f"/{relative}/":
            findings.append(
                {
                    "rule_id": "forbidden_directory",
                    "severity": "MAJOR",
                    "location": relative,
                    "detail": f"{name} must not be delivered",
                }
            )
    if relative.endswith(".pdf"):
        for key in PDF_METADATA_KEYS:
            if key in data:
                findings.append(
                    {
                        "rule_id": "pdf_metadata",
                        "severity": "MAJOR",
                        "location": relative,
                        "detail": f"PDF metadata key {key.decode()} present",
                    }
                )
    if relative.lower().endswith((".jpg", ".jpeg", ".png")):
        if EXIF_MARKER in data:
            software = EXIF_SOFTWARE in data
            gps = EXIF_GPS in data
            if gps or software:
                findings.append(
                    {
                        "rule_id": "image_exif_identity",
                        "severity": "MAJOR",
                        "location": relative,
                        "detail": f"image EXIF exposes {'GPS' if gps else ''} "
                        f"{'Software' if software else ''}".strip(),
                    }
                )
    if relative.lower().endswith(NESTED_ARCHIVE_SUFFIXES):
        findings.append(
            {
                "rule_id": "nested_archive",
                "severity": "MAJOR",
                "location": relative,
                "detail": "nested archive members are not scanned and must not be delivered",
            }
        )
    for rule_id, pattern in SECRET_PATTERNS:
        # 每个模式报告文件内全部命中（上限防日志膨胀），避免同文件多处
        # 泄漏被"只报第一处"少报。
        for match in list(pattern.finditer(data))[:16]:
            findings.append(
                {
                    "rule_id": rule_id,
                    "severity": "CRITICAL",
                    "location": relative,
                    "detail": f"secret-like content at byte offset {match.start()}",
                }
            )
    for match in ABSOLUTE_PATH_PATTERN.finditer(data):
        findings.append(
            {
                "rule_id": "absolute_path_leak",
                "severity": "MAJOR",
                "location": relative,
                "detail": f"absolute path at byte offset {match.start()}",
            }
        )
    return findings


def scan_file(path: Path, relative: str) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise IntegrityError(f"cannot read file for privacy scan: {relative}") from error
    return {
        "relative_path": relative,
        "sha256": _sha256(data),
        "findings": _scan_bytes(data, relative),
    }


def scan_manifest_files(runtime: Runtime, items: Any) -> dict[str, Any]:
    """Scan every delivery-manifest file and aggregate a deterministic report."""
    if not isinstance(items, list) or not items:
        raise IntegrityError("privacy scan requires delivery manifest files")
    files: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise IntegrityError("delivery manifest entries must be objects")
        relative = item.get("path")
        digest = item.get("sha256")
        if not isinstance(relative, str) or not relative:
            raise IntegrityError("delivery manifest entry lacks a path")
        if not isinstance(digest, str):
            raise IntegrityError("delivery manifest entry lacks a hash")
        from .canonical import resolve_within

        path = resolve_within(
            runtime.project_root,
            runtime.project_root / relative,
            must_exist=True,
        )
        scanned = scan_file(path, relative)
        if scanned["sha256"] != digest:
            raise IntegrityError(
                f"delivery file changed before privacy scan: {relative}"
            )
        files.append(scanned)
    hard = [
        finding
        for file in files
        for finding in file["findings"]
        if finding["severity"] in {"CRITICAL", "MAJOR"}
    ]
    return {
        "checker_version": CHECKER_VERSION,
        "status": "PASS" if not hard else "FAIL",
        "files": files,
    }


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
