from __future__ import annotations

import json
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical import atomic_write_json, canonical_json_bytes, sha256_bytes
from .errors import ConfigError, IntegrityError
from .integrity import build_policy_lock, verify_policy_lock
from .ledger import Ledger
from .registry import Registry
from .quality import normalize_profile
from .state_machine import STAGES, Workflow


@dataclass(frozen=True)
class Runtime:
    skill_root: Path
    project_root: Path
    contract: dict[str, Any]
    policy_lock: dict[str, Any]
    ledger: Ledger
    registry: Registry
    workflow: Workflow

    @property
    def run_id(self) -> str:
        return str(self.contract["run_id"])


def installed_skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_json_object(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read JSON object: {source}") from error
    if not isinstance(value, dict):
        raise ConfigError(f"expected JSON object: {source}")
    return value


def _project_directories() -> tuple[str, ...]:
    return (
        ".mmflow/registry",
        ".mmflow/reports",
        ".mmflow/checkpoints",
        "inputs",
        "code",
        "configs",
        "runs",
        "manuscript",
        "deliverables",
        "support-materials",
    )


def initialize_project(
    project_root: Path | str,
    competition: str,
    edition: str,
    skill_root: Path | str | None = None,
    quality_profile: str | None = None,
) -> Runtime:
    root = Path(project_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise ConfigError("project root must be a directory")
    if not isinstance(competition, str) or not competition.strip():
        raise ConfigError("init requires a non-empty competition")
    if not isinstance(edition, str) or not edition.strip():
        raise ConfigError("init requires a non-empty edition")
    if (root / ".mmflow" / "contract.json").exists():
        raise IntegrityError("project is already initialized")
    skill = Path(skill_root or installed_skill_root()).resolve(strict=True)
    selected_quality_profile = normalize_profile(skill, quality_profile)
    policy_lock = build_policy_lock(skill)
    for relative in _project_directories():
        (root / relative).mkdir(parents=True, exist_ok=True)
    run_id = "run_" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    contract = {
        "contract_version": 2,
        "run_id": run_id,
        "competition": competition.strip(),
        "edition": edition.strip(),
        "created_at": now.isoformat(),
        "created_timezone": str(datetime.now().astimezone().tzinfo),
        "skill_version": "2.0.0",
        "quality_profile": selected_quality_profile,
        "python_version": sys.version,
        "project_root_name": root.name,
    }
    atomic_write_json(root / ".mmflow/contract.json", contract)
    atomic_write_json(root / ".mmflow/policy-lock.json", policy_lock)
    ledger = Ledger(root, policy_lock["policy_sha256"])
    ledger.initialize(run_id)
    contract_digest = sha256_bytes(canonical_json_bytes(contract))
    ledger.append(
        run_id,
        "PROJECT_CONTRACT_COMMITTED",
        {"contract_sha256": contract_digest},
    )
    registry = Registry(
        root,
        ledger,
        run_id,
        evidence_stage_matrix=_evidence_stage_matrix(skill),
    )
    workflow = Workflow(root, ledger, run_id)
    workflow.state()
    _bind_registry_epoch(registry, workflow)
    return Runtime(skill, root, contract, policy_lock, ledger, registry, workflow)


_LAST_LOADED_RUNTIME = None


def _remember_loaded_runtime(runtime) -> None:
    global _LAST_LOADED_RUNTIME
    _LAST_LOADED_RUNTIME = runtime


def refresh_last_loaded_integrity_cache() -> None:
    """Refresh the trust frontier for the most recent load_runtime result.

    Called by the CLI after a command completes so the next command can trust
    the post-mutation frontier without a deep replay.  Best-effort only.
    """
    if _LAST_LOADED_RUNTIME is not None:
        refresh_integrity_cache(_LAST_LOADED_RUNTIME)


def _load_integrity_cache(root: Path) -> dict[str, Any] | None:
    """Best-effort read of the last deeply verified frontier marker."""
    path = root / ".mmflow" / "integrity-cache.json"
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def load_runtime(
    project_root: Path | str,
    skill_root: Path | str | None = None,
) -> Runtime:
    try:
        root = Path(project_root).resolve(strict=True)
    except OSError as error:
        raise ConfigError(f"project root does not exist: {project_root}") from error
    if not root.is_dir():
        raise ConfigError("project root must be a directory")
    skill = Path(skill_root or installed_skill_root()).resolve(strict=True)
    contract = read_json_object(root / ".mmflow/contract.json")
    policy_lock = read_json_object(root / ".mmflow/policy-lock.json")
    if int(contract.get("contract_version", 0)) < 2 or str(
        contract.get("skill_version", "")
    ) != "2.0.0":
        raise ConfigError(
            "project uses a v1 contract; v1 projects stay read-only and are "
            "not silently upgraded. Run `mmflow migrate --project <root> "
            "--dry-run` to see the explicit migration plan."
        )
    normalize_profile(skill, contract.get("quality_profile"))
    run_id = contract.get("run_id")
    if not isinstance(run_id, str) or not run_id.startswith("run_"):
        raise IntegrityError("project contract has invalid run_id")
    verify_policy_lock(skill, policy_lock)
    policy_sha256 = policy_lock.get("policy_sha256")
    if not isinstance(policy_sha256, str):
        raise IntegrityError("policy lock has no valid policy_sha256")
    ledger = Ledger(root, policy_sha256)
    ledger.recover()
    head = ledger.head()
    if head["run_id"] != run_id:
        raise IntegrityError("contract and ledger run_id differ")
    contract_digest = sha256_bytes(canonical_json_bytes(contract))
    cached = _load_integrity_cache(root)
    state_path_check = root / ".mmflow" / "state.json"
    state_hash_now = (
        sha256_bytes(state_path_check.read_bytes())
        if state_path_check.is_file()
        else None
    )
    trusted = (
        cached is not None
        and cached.get("cache_version") == 1
        and isinstance(cached.get("head_sha256"), str)
        and cached.get("contract_sha256") == contract_digest
        and cached.get("state_sha256") == state_hash_now
        and ledger.contains_event_hash(cached.get("tip_event_sha256"))
        and not (root / ".mmflow" / "ledger-transaction.json").exists()
    )
    if not trusted:
        # Deep path: full hash-chain walk, contract commitment scan and
        # registry file-set reconciliation run whenever the verified frontier
        # moved or no prior verification is recorded.  Gate/audit/release paths
        # additionally re-run deep checks explicitly.
        ledger.validate()
    if trusted:
        contract_commitment_ok = True
    else:
        commitments = [
            event
            for event in ledger.read_events()
            if event.get("event_type") == "PROJECT_CONTRACT_COMMITTED"
        ]
        contract_commitment_ok = (
            len(commitments) == 1
            and commitments[0].get("payload", {}).get("contract_sha256")
            == contract_digest
        )
    if not contract_commitment_ok:
        raise IntegrityError("project contract does not match its immutable ledger commitment")
    registry = Registry(
        root,
        ledger,
        run_id,
        evidence_stage_matrix=_evidence_stage_matrix(skill),
    )
    if not trusted:
        registry.validate_integrity()
    workflow = Workflow(root, ledger, run_id)
    workflow._trusted_view_ok = bool(trusted)
    workflow.state()
    _bind_registry_epoch(registry, workflow)
    new_cache = {
        "cache_version": 1,
        "head_sha256": head["head_sha256"],
        "tip_event_sha256": head["event_sha256"],
        "contract_sha256": contract_digest,
        "state_sha256": (
            sha256_bytes(state_path_check.read_bytes())
            if state_path_check.is_file()
            else None
        ),
    }
    if cached != new_cache:
        atomic_write_json(root / ".mmflow" / "integrity-cache.json", new_cache)
    _remember_loaded_runtime(
        Runtime(skill, root, contract, policy_lock, ledger, registry, workflow)
    )
    return _LAST_LOADED_RUNTIME


def refresh_integrity_cache(runtime) -> None:
    """Refresh the trust frontier after a mutating command completes.

    Best-effort by design: the cache only decides whether the next load may
    skip deep validation; any mismatch or write failure falls back to the
    full hash-chain walk on the following command.
    """
    try:
        head = runtime.ledger.head()
        state_path = runtime.project_root / ".mmflow" / "state.json"
        cached = _load_integrity_cache(runtime.project_root) or {}
        new_cache = {
            "cache_version": 1,
            "head_sha256": head["head_sha256"],
            "tip_event_sha256": head["event_sha256"],
            "contract_sha256": sha256_bytes(canonical_json_bytes(runtime.contract)),
            "state_sha256": (
                sha256_bytes(state_path.read_bytes()) if state_path.is_file() else None
            ),
        }
        if {k: v for k, v in cached.items() if k in new_cache} != new_cache:
            atomic_write_json(
                runtime.project_root / ".mmflow" / "integrity-cache.json", new_cache
            )
    except Exception:
        # Cache is advisory; correctness never depends on it.
        pass


def export_claims_payload(runtime, question: str | None = None) -> dict[str, Any]:
    """Export VALID claims as the qa_cards defense-card input document."""
    identities = runtime.registry._committed_identity_map()
    claims: list[dict[str, Any]] = []
    for record in runtime.registry.iter_latest("claim"):
        payload = record.get("payload", {})
        if payload.get("status") != "VALID":
            continue
        qid = payload.get("question_id")
        if question is not None and qid != question:
            continue
        grouped: dict[str, list[str]] = {"result": [], "formula": [], "citation": []}
        for support_id in payload.get("supports", []):
            kind = identities.get(support_id)
            if kind in grouped:
                grouped[kind].append(support_id)
        scope = payload.get("scope")
        entry: dict[str, Any] = {
            "claim_id": payload.get("claim_id"),
            "statement": payload.get("statement", ""),
            "supporting_result_ids": grouped["result"],
            "formula_ids": grouped["formula"],
            "citation_ids": grouped["citation"],
            "limitations": [scope] if scope else [],
        }
        if qid:
            entry["question_id"] = qid
        claims.append(entry)
    return {
        "schema": "mmflow-defense-cards-input/v1",
        "competition": runtime.contract.get("competition"),
        "edition": runtime.contract.get("edition"),
        "claims": claims,
    }


def load_policy(runtime: Runtime, name: str) -> dict[str, Any]:
    if Path(name).name != name or not name.endswith(".json"):
        raise ConfigError("policy name must be a direct JSON filename")
    return read_json_object(runtime.skill_root / "scripts/mmflow_core/policies" / name)


def _evidence_stage_matrix(skill_root: Path) -> dict[str, list[str]]:
    """Load the evidence type -> allowed registration stages matrix."""
    policy = read_json_object(
        skill_root / "scripts/mmflow_core/policies" / "evidence-v1.json"
    )
    matrix = policy.get("evidence_stage_matrix")
    if not isinstance(matrix, dict):
        raise IntegrityError("evidence policy has no stage matrix")
    return {
        str(evidence_type): [str(stage) for stage in stages]
        for evidence_type, stages in matrix.items()
        if isinstance(stages, list)
    }


def _bind_registry_epoch(registry: Registry, workflow: Workflow) -> None:
    registry.set_stage_epoch_source(
        lambda stage: workflow.snapshot()["stage_epochs"].get(stage, 0)
    )


def next_stage(runtime: Runtime) -> dict[str, Any]:
    """Return one unique machine action: the only legal next step.

    The AI executes the returned ``action`` and nothing else.  Beyond the
    stage identity the payload carries what is missing, what is invalid,
    which reference files to read, the minimum fix, the re-run scope and the
    current redlines, so the AI never has to infer recovery from prose.
    """
    state = runtime.workflow.state()
    stages = load_policy(runtime, "stages-v1.json").get("stages")
    if not isinstance(stages, list):
        raise IntegrityError("stage policy has no stage list")
    by_id = {
        entry.get("id"): entry
        for entry in stages
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    if set(by_id) != set(STAGES):
        raise IntegrityError("stage policy does not match workflow stages")
    evidence_policy = load_policy(runtime, "evidence-v1.json")
    stage_requirements = evidence_policy.get("stage_requirements", {})
    redline_ids = set(evidence_policy.get("redlines", []))

    def references_for(stage: str) -> list[str]:
        entry = by_id[stage]
        declared = entry.get("references")
        if isinstance(declared, list) and declared and all(
            isinstance(item, str) for item in declared
        ):
            return list(declared)
        reference = entry.get("reference")
        return [reference] if isinstance(reference, str) else []

    def active_redlines() -> list[str]:
        return sorted(
            {
                finding["payload"]["redline_id"]
                for finding in runtime.registry.iter_latest("finding")
                if finding["payload"].get("status") == "VALID"
                and finding["payload"].get("finding_status") == "OPEN"
                and finding["payload"].get("redline_id") in redline_ids
            }
        )

    def missing_evidence(stage: str) -> list[str]:
        definition = stage_requirements.get(stage)
        required = definition.get("evidence_types") if isinstance(definition, dict) else []
        if not isinstance(required, list):
            return []
        present = {
            str(record["payload"].get("evidence_type"))
            for record in runtime.registry.iter_latest("evidence")
            if record["payload"].get("status") == "VALID"
        }
        return [item for item in required if item not in present]

    def invalid_entities() -> list[str]:
        return sorted(
            record["entity_id"]
            for kind in (
                "artifact",
                "execution",
                "result",
                "claim",
                "formula",
                "figure",
                "citation",
                "finding",
                "evidence",
            )
            for record in runtime.registry.iter_latest(kind)
            if record["payload"].get("status") in {"STALE", "INVALID", "REVOKED"}
        )

    def earliest_invalid_stage() -> str | None:
        stages_seen: list[str] = []
        for kind in ("execution", "result", "claim", "figure", "evidence", "finding"):
            for record in runtime.registry.iter_latest(kind):
                payload = record["payload"]
                if payload.get("status") in {"STALE", "INVALID", "REVOKED"}:
                    stage = payload.get("stage") or record.get("created_stage")
                    if isinstance(stage, str) and stage in STAGES:
                        stages_seen.append(stage)
        return min(stages_seen, key=lambda item: int(item[1:])) if stages_seen else None

    def base(stage: str | None, status: str, next_command: str | None) -> dict[str, Any]:
        return {
            "stage": stage,
            "status": status,
            "stage_epoch": (
                state["stage_epochs"][stage] if stage is not None else None
            ),
            "references": references_for(stage) if stage is not None else [],
            "next_command": next_command,
            "missing_evidence": missing_evidence(stage) if stage is not None else [],
            "invalid_entities": invalid_entities(),
            "rerun_scope": [] if stage is None else _rerun_scope(stage),
            "blocker": state.get("blocked"),
            "active_redlines": active_redlines(),
        }

    def next_stage_of(view: dict[str, Any]) -> str:
        for candidate in STAGES:
            if view["stages"][candidate] in {"NOT_STARTED", "INVALIDATED"}:
                return candidate
        raise IntegrityError("workflow has no legal next stage")

    if state["complete"]:
        return base(None, "COMPLETE", None)
    active = state["active_stage"]
    if active is not None:
        return base(active, state["stages"][active], f"gate {active}")
    blocked = [
        stage for stage, status in state["stages"].items() if status == "BLOCKED"
    ]
    if blocked:
        if len(blocked) != 1:
            raise IntegrityError("workflow contains multiple blocked stages")
        stage = blocked[0]
        blocker = state.get("blocked")
        command = (
            str(blocker["payload"].get("resume_command"))
            if isinstance(blocker, dict)
            and isinstance(blocker.get("payload"), dict)
            and blocker["payload"].get("resume_command")
            else "resume --resolve-blocked --evidence <post-block evidence id>"
        )
        return base(stage, "BLOCKED", command)
    integrity_failures = [
        stage_name
        for stage_name, status in state["stages"].items()
        if status == "INTEGRITY_FAILURE"
    ]
    if integrity_failures:
        # M-F4: an INTEGRITY_FAILURE stage must NOT be skipped by `next`.
        # Skipping it advertised `begin <later stage>`, which always fails,
        # trapping the workflow in a contradiction loop.  The only legal
        # escape is a rollback of the failed stage itself, so surface that
        # command explicitly instead.
        failed_stage = min(integrity_failures, key=lambda item: int(item[1:]))
        action = base(
            failed_stage,
            "INTEGRITY_FAILURE",
            f"rollback {failed_stage} --reason \"recover from INTEGRITY_FAILURE\""
            " then rerun doctor/audit before resuming professional work",
        )
        action["blocker"] = {
            "type": "integrity_failure",
            "stage": failed_stage,
            "resume_command": (
                f"rollback {failed_stage} --reason recover-integrity-failure"
            ),
        }
        return action
    stage = next_stage_of(state)
    return base(stage, state["stages"][stage], f"begin {stage}")


def _rerun_scope(stage: str) -> list[str]:
    start = int(stage[1:])
    return [f"P{index}" for index in range(start, 12)]


def create_checkpoint(runtime: Runtime) -> dict[str, Any]:
    head = runtime.ledger.head()
    sequence = int(head["sequence"])
    state = runtime.workflow.state()
    registry_records: list[list[str]] = []
    for kind in (
        "artifact",
        "execution",
        "result",
        "claim",
        "formula",
        "figure",
        "citation",
        "finding",
        "evidence",
        "split",
    ):
        for record in runtime.registry.iter_latest(kind):
            registry_records.append(
                [kind, record["entity_id"], record["record_sha256"]]
            )
    next_action = next_stage(runtime)
    open_risks = sorted(
        record["entity_id"]
        for record in runtime.registry.iter_latest("finding")
        if record["payload"].get("status") == "VALID"
        and record["payload"].get("finding_status") == "OPEN"
    )
    unresolved_transactions = (
        (runtime.project_root / ".mmflow" / "ledger-transaction.json").is_file()
        or (runtime.project_root / ".mmflow" / "registry-journal.json").is_file()
    )
    snapshot = {
        "checkpoint_version": 2,
        "run_id": runtime.run_id,
        "ledger_sequence": sequence,
        "ledger_head_sha256": head["head_sha256"],
        "state": state,
        "registry_fingerprint": sha256_bytes(
            canonical_json_bytes(sorted(registry_records))
        ),
        "next": next_action,
        "work_queue": {
            "missing_evidence": next_action.get("missing_evidence", []),
            "invalid_entities": next_action.get("invalid_entities", []),
            "rerun_scope": next_action.get("rerun_scope", []),
            "open_risks": open_risks,
            "unresolved_transactions": unresolved_transactions,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = runtime.project_root / ".mmflow/checkpoints" / f"{sequence:06d}.json"
    if path.exists():
        raise IntegrityError("checkpoint for this ledger sequence already exists")
    atomic_write_json(path, snapshot)
    runtime.ledger.append(
        runtime.run_id,
        "CHECKPOINT_CREATED",
        {
            "checkpoint_path": path.relative_to(runtime.project_root).as_posix(),
            "checkpoint_sha256": sha256_bytes(canonical_json_bytes(snapshot)),
        },
        stage=state["active_stage"],
    )
    return snapshot


def _minimal_pdf_bytes() -> bytes:
    """Build a tiny, well-formed single-page PDF for the parse probe.

    Offsets in the xref table are computed so strict parsers accept it.
    """
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 144 144] >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        "startxref\n" + str(xref_at) + "\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


def _parse_probe(provider_module: str) -> tuple[bool, str]:
    """Try to actually open and page-count the embedded minimal PDF."""
    sample = _minimal_pdf_bytes()
    try:
        if provider_module == "pypdf":
            from io import BytesIO

            from pypdf import PdfReader

            reader = PdfReader(BytesIO(sample))
            assert len(reader.pages) == 1
        elif provider_module == "fitz":
            import fitz

            document = fitz.open(stream=sample, filetype="pdf")
            assert document.page_count == 1
        elif provider_module == "pdfminer.high_level":
            from io import BytesIO

            from pdfminer.high_level import extract_text

            extract_text(BytesIO(sample))
        else:
            return False, f"unknown provider module {provider_module}"
        return True, "parsed embedded minimal PDF"
    except Exception as error:  # noqa: BLE001 - report any parse failure
        return False, f"{type(error).__name__}: {error}"


def _probe_pdf_capability() -> dict[str, Any]:
    """Read-only PDF capability probe (P8/P10/P11 read PDF facts).

    Two levels: import availability, then an actual parse of an embedded
    minimal well-formed PDF - a library that imports but cannot parse is
    reported as unavailable instead of failing later at P8.
    """
    providers = (
        ("pypdf", "pypdf.PdfReader"),
        ("fitz", "PyMuPDF"),
        ("pdfminer.high_level", "pdfminer.six"),
    )
    failures: list[str] = []
    for module_name, provider in providers:
        try:
            __import__(module_name)
        except ImportError:
            continue
        parsed, detail = _parse_probe(module_name)
        if parsed:
            return {
                "available": True,
                "provider": provider,
                "module": module_name,
                "parse_check": "pass",
                "note": "page counts and metadata checks are possible locally",
            }
        failures.append(f"{provider}: {detail}")
    note = ("no local PDF library found; install pypdf (pip install pypdf) "
            "so P8/P10/P11 can verify page counts and metadata")
    if failures:
        note = "importable libraries failed the parse probe - " + "; ".join(
            failures
        ) + ". " + note
    return {
        "available": False,
        "provider": None,
        "module": None,
        "parse_check": "fail" if failures else "not_attempted",
        "note": note,
    }


def _probe_spreadsheet_capability() -> dict[str, Any]:
    """Read-only import probe for tabular-data libraries (P1/P3 readers)."""
    providers = (("pandas", "pandas"), ("openpyxl", "openpyxl"))
    available: list[str] = []
    missing: list[str] = []
    for module_name, provider in providers:
        try:
            __import__(module_name)
            available.append(provider)
        except ImportError:
            missing.append(provider)
    return {
        "available": bool(available),
        "providers": available,
        "missing": missing,
        "note": (
            "tabular inputs can be read with the listed providers"
            if available
            else "install pandas/openpyxl to read spreadsheet attachments"
        ),
    }


def _probe_network_capability(timeout_seconds: float = 3.0) -> dict[str, Any]:
    """Explicit opt-in connectivity probe (never runs by default).

    Doctor performs no external traffic unless ``probe_network=True``; when
    enabled it issues one short HEAD request and reports reachability so P0
    can register literature/rule verification capability honestly.
    """
    import urllib.error
    import urllib.request

    target = "https://www.comap.cn/"
    started = time.monotonic()
    try:
        request = urllib.request.Request(target, method="HEAD")
        urllib.request.urlopen(request, timeout=timeout_seconds)
    except Exception as error:  # noqa: BLE001 - any failure is a capability fact
        return {
            "status": "unavailable",
            "probed": True,
            "target": target,
            "detail": f"{type(error).__name__}: {error}",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "note": (
                "network verification is unavailable; prefer locally cached "
                "rule snapshots and register the limitation at P0"
            ),
        }
    return {
        "status": "available",
        "probed": True,
        "target": target,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "note": "one HEAD request succeeded; rule pages must still be snapshotted",
    }


def doctor(
    project_root: Path | str,
    probe_write: bool = False,
    probe_network: bool = False,
) -> dict[str, Any]:
    """Read-only capability report with honest isolation disclosure.

    The default run never creates the project directory, never writes a
    probe file and never generates traffic.  ``probe_write=True`` and
    ``probe_network=True`` are explicit opt-ins that temporarily verify
    filesystem writability and outbound connectivity respectively.  The
    isolation section states plainly that the runner provides
    project-directory attestation, not an operating system sandbox.
    """
    root = Path(project_root).resolve()
    writable: bool | None = None
    probe: Path | None = None
    if probe_write:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".mmflow-doctor-write-probe"
        if probe.exists():
            raise IntegrityError("doctor probe path already exists")
        try:
            probe.write_bytes(b"probe")
            writable = probe.read_bytes() == b"probe"
        finally:
            if probe.is_file():
                probe.unlink()
    exists = root.is_dir()
    xelatex = shutil.which("xelatex")
    pandoc = shutil.which("pandoc")
    network_report = (
        _probe_network_capability()
        if probe_network
        else {
            "status": "not_probed",
            "probed": False,
            "reason": (
                "doctor does not create external traffic by default; "
                "re-run with --probe-network for an explicit check"
            ),
        }
    )
    return {
        "python": {
            "available": True,
            "version": sys.version,
            "executable": sys.executable,
        },
        "filesystem": {
            "project_root": str(root),
            "exists": exists,
            "writable": writable,
            "write_probe": probe_write,
        },
        "spreadsheets": _probe_spreadsheet_capability(),
        "xelatex": {"available": xelatex is not None, "path": xelatex},
        "pandoc": {"available": pandoc is not None, "path": pandoc},
        "pdf": _probe_pdf_capability(),
        "network": network_report,
        "independent_review": {
            "status": "user_declared",
            "reason": (
                "true independent review depends on separately executed "
                "agents or external reviewers; the host cannot detect it "
                "and must be declared by the user at P0/P10"
            ),
        },
        "isolation": {
            "level": "project-directory-attestation",
            "os_sandbox": False,
            "network_isolation": False,
            "external_filesystem_isolation": False,
            "process_tree_isolation": "subprocess-only",
            "single_writer_lock": True,
            "disclosure": (
                "the runner attests which commands ran, which project inputs "
                "were used, which outputs appeared and their hashes; it does "
                "not block program access outside the project directory, "
                "network access, or child-process escape. Real isolation "
                "requires a host container, VM or OS permission sandbox."
            ),
        },
    }
