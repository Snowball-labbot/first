from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

from .canonical import (
    atomic_write_json,
    canonical_json_bytes,
    resolve_within,
    sha256_bytes,
    sha256_file,
)
from .errors import ConfigError, IntegrityError, UntrustedArtifactError
from .ledger import Ledger


ID_FIELDS = {
    "artifact": "artifact_id",
    "execution": "execution_id",
    "result": "result_id",
    "claim": "claim_id",
    "formula": "formula_id",
    "figure": "figure_id",
    "citation": "citation_id",
    "finding": "finding_id",
    "evidence": "evidence_id",
    "split": "split_id",
}
KIND_ALIASES = {
    "artifacts": "artifact",
    "executions": "execution",
    "results": "result",
    "claims": "claim",
    "formulas": "formula",
    "figures": "figure",
    "citations": "citation",
    "findings": "finding",
    "evidences": "evidence",
    "splits": "split",
}
KIND_DIRECTORIES = {
    "artifact": "artifacts",
    "execution": "executions",
    "result": "results",
    "claim": "claims",
    "formula": "formulas",
    "figure": "figures",
    "citation": "citations",
    "finding": "findings",
    "evidence": "evidence",
    "split": "splits",
}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_CLASSES = {
    "production",
    "exploratory",
    "demo",
    "fixture",
    "external",
    "unattested",
}
ENTITY_STATUSES = {"VALID", "STALE", "INVALID", "REVOKED"}
# Status is an auditable lifecycle, not a free-form label.  A status can only
# move toward less trust; a replacement run receives a new entity ID.
STATUS_RANK = {"VALID": 0, "STALE": 1, "INVALID": 2, "REVOKED": 3}
DIRECTIONS = {
    "higher_is_better",
    "lower_is_better",
    "target_is_best",
    "not_applicable",
}
CLAIM_TYPES = {
    "computed",
    "observational",
    "inferential",
    "theoretical",
    "external",
    "recommendation",
    "limitation",
}
CLAIM_STRENGTHS = {
    "confirmed",
    "supported",
    "exploratory",
    "hypothesis",
    "unsupported",
}
RESULT_KINDS = {
    "scalar",
    "vector",
    "table",
    "category",
    "set",
}
SPLIT_KINDS = {"time", "group", "spatial", "random", "custom"}
PREPROCESSING_FIT_SCOPES = {"train_only", "none"}
FORMULA_TYPES = {"theoretical", "empirical", "optimization", "statistical", "mechanistic"}
CITATION_ACCESS_LEVELS = {"public", "subscribed", "private", "deleted"}
CITATION_VERIFICATION_STATUSES = {
    "verified",
    "corrected",
    "unverified",
    "failed",
    "retracted",
}
CITATION_SOURCE_ROLES = {"official_rule", "academic", "dataset", "web", "other"}
INELIGIBLE_FINAL_CLASSES = {"demo", "fixture", "unattested", "exploratory"}

# These fields are fixed before a child process is launched.  Their canonical
# digest is committed by EXECUTION_STARTED and repeated in the immutable
# execution record, preventing the post-run record from rewriting the command,
# inputs, comparison contract, or execution environment.
EXECUTION_INTENT_FIELDS = (
    "execution_id",
    "run_id",
    "attempt_id",
    "attempt_path",
    "stage",
    "question",
    "role",
    "artifact_class",
    "command",
    "working_directory",
    "resolved_executable",
    "executable_sha256",
    "environment_lock",
    "source_imports",
    "source_snapshots",
    "source_artifact_ids",
    "dataset_split_ids",
    "random_protocol",
    "expected_outputs",
    "comparison_policies",
    "timeout_seconds",
    "requested_output_encoding",
    "environment",
    "platform",
    "python_version",
    "policy_sha256",
)


def execution_intent_sha256(payload: dict[str, Any]) -> str:
    """Return the canonical commitment for the pre-launch execution intent."""
    missing = [field for field in EXECUTION_INTENT_FIELDS if field not in payload]
    if missing:
        raise ConfigError("execution intent missing: " + ", ".join(missing))
    intent = {field: payload[field] for field in EXECUTION_INTENT_FIELDS}
    return sha256_bytes(canonical_json_bytes(intent))


class Registry:
    def __init__(
        self,
        project_root: Path | str,
        ledger: Ledger,
        run_id: str,
        evidence_stage_matrix: dict[str, list[str]] | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.root = self.project_root / ".mmflow" / "registry"
        self.ledger = ledger
        self.run_id = run_id
        self.evidence_stage_matrix = evidence_stage_matrix or {}
        self._epoch_source = None
        self.journal_path = self.project_root / ".mmflow" / "registry-journal.json"
        # Memoized REGISTRY_RECORDED event scan, keyed by the ledger head that
        # produced it.  Turns O(events) lookups (_committed_versions, identity
        # map, execution events) into amortized single-pass work per command.
        self._event_cache_head: str | None = None
        self._event_cache: list[dict[str, Any]] | None = None
        # Memoized committed version records keyed by (head, kind, entity).
        # Every registry mutation appends a REGISTRY_RECORDED event, which
        # changes the ledger head and therefore invalidates the cache, so
        # correctness never depends on manual eviction.
        self._version_cache_head: str | None = None
        self._version_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        # Memoized assembled latest-record lists keyed by ledger head, so
        # hot loops (`next`/`gate`/`audit` 扫描全部 evidence/artifact) 不再
        # 每次调用重建 identity map 并逐实体解析版本；失效模型与上方缓存
        # 相同——任何登记/修订都会推进 head，从而整体失效。对外仍逐条
        # deepcopy 返回，调用方无法污染内部状态。
        self._latest_list_cache_head: str | None = None
        self._latest_list_cache: dict[str, list[dict[str, Any]]] = {}

    def _registry_events(self) -> list[dict[str, Any]]:
        head = self.ledger.head()
        head_key = head["head_sha256"]
        if self._event_cache is None or self._event_cache_head != head_key:
            self._event_cache = self.ledger.read_events()
            self._event_cache_head = head_key
        return self._event_cache

    def set_stage_epoch_source(self, source) -> None:
        """Bind a callable ``(stage) -> int`` returning the current stage epoch.

        The state machine owns the epoch counter; the Registry only records
        the value so gates can enforce evidence freshness per epoch.
        """
        self._epoch_source = source

    def _resolve_epoch(self, stage: str | None) -> int | None:
        if stage is None or self._epoch_source is None:
            return None
        return int(self._epoch_source(stage))

    @staticmethod
    def normalize_kind(kind: str) -> str:
        normalized = KIND_ALIASES.get(kind, kind)
        if normalized not in ID_FIELDS:
            raise ConfigError(f"unsupported registry kind: {kind}")
        return normalized

    def _identity(self, kind: str, payload: dict[str, Any]) -> str:
        kind = self.normalize_kind(kind)
        entity_id = payload.get(ID_FIELDS[kind])
        if not isinstance(entity_id, str) or not ID_PATTERN.fullmatch(entity_id):
            raise ConfigError(f"invalid {ID_FIELDS[kind]}")
        return entity_id

    @staticmethod
    def _require_string(payload: dict[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{field} must be a non-empty string")
        return value

    @staticmethod
    def _require_string_list(payload: dict[str, Any], field: str) -> list[str]:
        value = payload.get(field)
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            raise ConfigError(f"{field} must be a list of non-empty strings")
        return value

    @staticmethod
    def _is_link_or_junction(path: Path, root: Path) -> bool:
        current = path
        is_junction = getattr(os.path, "isjunction", lambda _path: False)
        while True:
            if current.is_symlink() or is_junction(current):
                return True
            if current == root:
                return False
            if root not in current.parents:
                return True
            current = current.parent

    def _validate_artifact(self, payload: dict[str, Any], resolve_dependencies: bool) -> None:
        artifact_class = payload.get("artifact_class")
        if artifact_class not in ARTIFACT_CLASSES:
            raise ConfigError("invalid artifact class")
        self._require_string(payload, "artifact_type")
        relative = self._require_string(payload, "relative_path")
        if "\\" in relative:
            raise ConfigError("artifact relative_path must use POSIX separators")
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ConfigError("artifact relative_path must stay within the project")
        digest = payload.get("sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise ConfigError("invalid artifact SHA-256")
        path = resolve_within(
            self.project_root,
            self.project_root / relative_path,
            must_exist=payload.get("status") == "VALID",
        )
        if payload.get("status") == "VALID":
            if not path.is_file() or self._is_link_or_junction(path, self.project_root):
                raise UntrustedArtifactError("artifact must be a regular in-project file")
            if sha256_file(path) != digest:
                raise IntegrityError("artifact content does not match registered SHA-256")
            if payload.get("size_bytes") != path.stat().st_size:
                raise IntegrityError("artifact size does not match registered size")
        elif path.exists() and self._is_link_or_junction(path, self.project_root):
            raise UntrustedArtifactError("artifact path may not become a link or junction")
        self._require_string_list(payload, "inputs")
        normalized = path.relative_to(self.project_root).as_posix()
        forbidden = ("legacy", "templates/examples", "tests/fixtures")
        if artifact_class == "production" and any(
            normalized == prefix or normalized.startswith(prefix + "/")
            for prefix in forbidden
        ):
            raise UntrustedArtifactError("production artifact uses a forbidden source path")
        if not resolve_dependencies:
            return
        for dependency in payload["inputs"]:
            record = self.find_entity(dependency)
            if record["payload"].get("status") != "VALID":
                raise IntegrityError(f"artifact input is not valid: {dependency}")
        if artifact_class == "production":
            execution_id = payload.get("execution_id")
            if payload.get("artifact_type") == "delivery_package":
                # The controlled packaging command itself is the producer; no
                # child-process execution exists for a package archive.
                pass
            elif not isinstance(execution_id, str):
                raise UntrustedArtifactError("production artifact requires execution_id")
            else:
                try:
                    execution = self.latest("execution", execution_id)["payload"]
                except IntegrityError as error:
                    raise UntrustedArtifactError(
                        "production artifact has no committed producer execution"
                    ) from error
                if (
                    execution.get("run_id") != self.run_id
                    or execution.get("status") != "VALID"
                    or execution.get("exit_code") != 0
                    or execution.get("artifact_class") != "production"
                ):
                    raise UntrustedArtifactError(
                        "production artifact requires a valid same-run production execution"
                    )

    def _validate_execution(self, payload: dict[str, Any], resolve_dependencies: bool) -> None:
        required = (
            "attempt_id",
            "attempt_path",
            "stage",
            "question",
            "role",
            "artifact_class",
            "command",
            "working_directory",
            "resolved_executable",
            "executable_sha256",
            "environment_lock",
            "source_imports",
            "source_snapshots",
            "source_artifact_ids",
            "dataset_split_ids",
            "random_protocol",
            "expected_outputs",
            "comparison_policies",
            "observed_outputs",
            "unexpected_outputs",
            "unexpected_outside_outputs",
            "missing_outputs",
            "created_files",
            "modified_files",
            "deleted_files",
            "timed_out",
            "interrupted",
            "launch_error",
            "exit_code",
            "stdout_raw_path",
            "stderr_raw_path",
            "stdout_raw_sha256",
            "stderr_raw_sha256",
            "stdout_decode",
            "stderr_decode",
            "started_at",
            "finished_at",
            "duration_seconds",
            "environment",
            "platform",
            "python_version",
            "policy_sha256",
            "timeout_seconds",
            "requested_output_encoding",
            "intent_sha256",
        )
        missing = [field for field in required if field not in payload]
        if missing:
            raise ConfigError("execution missing: " + ", ".join(missing))
        if not isinstance(payload["executable_sha256"], str) or not SHA256_PATTERN.fullmatch(
            payload["executable_sha256"]
        ):
            raise ConfigError("execution executable_sha256 must be a SHA-256 digest")
        if not isinstance(payload["environment_lock"], dict):
            raise ConfigError("execution environment_lock must be an object")
        if not isinstance(payload["source_imports"], dict):
            raise ConfigError("execution source_imports must be an object mapping file to imports")
        if payload["artifact_class"] not in ARTIFACT_CLASSES:
            raise ConfigError("invalid execution artifact class")
        if not isinstance(payload["command"], list) or not payload["command"]:
            raise ConfigError("execution command must be a non-empty argument list")
        for field in (
            "source_artifact_ids",
            "dataset_split_ids",
            "expected_outputs",
            "observed_outputs",
            "unexpected_outputs",
            "unexpected_outside_outputs",
            "missing_outputs",
            "created_files",
            "modified_files",
            "deleted_files",
        ):
            self._require_string_list(payload, field)
        exit_code = payload["exit_code"]
        process_did_not_finish_normally = (
            payload["timed_out"] is True
            or payload["interrupted"] is True
            or payload["launch_error"] is not None
        )
        if exit_code is None:
            if not process_did_not_finish_normally:
                raise ConfigError("execution without exit_code needs an explicit process failure state")
        elif isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise ConfigError("execution exit_code must be an integer or justified null")
        for field in ("stdout_raw_sha256", "stderr_raw_sha256"):
            if not SHA256_PATTERN.fullmatch(str(payload[field])):
                raise ConfigError(f"execution {field} is invalid")
        if not SHA256_PATTERN.fullmatch(str(payload["intent_sha256"])):
            raise ConfigError("execution intent_sha256 is invalid")
        if payload["intent_sha256"] != execution_intent_sha256(payload):
            raise IntegrityError("execution intent differs from its committed digest")
        if (
            isinstance(payload["timeout_seconds"], bool)
            or not isinstance(payload["timeout_seconds"], int)
            or payload["timeout_seconds"] <= 0
        ):
            raise ConfigError("execution timeout_seconds must be a positive integer")
        if payload["requested_output_encoding"] is not None and not isinstance(
            payload["requested_output_encoding"], str
        ):
            raise ConfigError("requested_output_encoding must be a string or null")
        if payload.get("status") == "VALID" and (
            payload["exit_code"] != 0
            or payload["timed_out"] is not False
            or payload["interrupted"] is not False
            or payload["launch_error"] is not None
            or payload["missing_outputs"]
            or payload["unexpected_outputs"]
            or payload["unexpected_outside_outputs"]
            or set(payload["expected_outputs"]) != set(payload["observed_outputs"])
        ):
            raise ConfigError("VALID execution contradicts its process or output record")
        if resolve_dependencies:
            for artifact_id in payload["source_artifact_ids"]:
                artifact = self.latest("artifact", artifact_id)["payload"]
                if artifact.get("status") != "VALID":
                    raise UntrustedArtifactError(f"execution source is invalid: {artifact_id}")
                if payload["artifact_class"] == "production" and artifact.get(
                    "artifact_class"
                ) in INELIGIBLE_FINAL_CLASSES:
                    raise UntrustedArtifactError(
                        f"production execution uses ineligible source: {artifact_id}"
                    )
            for split_id in payload["dataset_split_ids"]:
                split = self.latest("split", split_id)["payload"]
                if split.get("status") != "VALID":
                    raise IntegrityError(
                        f"execution split is not a current valid split: {split_id}"
                    )

    def _validate_execution_files(self, payload: dict[str, Any]) -> None:
        """Re-read the immutable execution evidence from the project filesystem."""
        attempt_path = payload.get("attempt_path")
        if not isinstance(attempt_path, str) or not attempt_path or "\\" in attempt_path:
            raise IntegrityError("execution attempt_path is not a POSIX relative path")
        logical_attempt = Path(attempt_path)
        if logical_attempt.is_absolute() or ".." in logical_attempt.parts:
            raise IntegrityError("execution attempt_path escapes the project")
        try:
            attempt = resolve_within(
                self.project_root, self.project_root / logical_attempt, must_exist=True
            )
        except OSError as error:
            raise IntegrityError("execution attempt directory is missing") from error
        if not attempt.is_dir() or self._is_link_or_junction(attempt, self.project_root):
            raise UntrustedArtifactError("execution attempt is not a regular project directory")
        expected_working = (logical_attempt / "sandbox").as_posix()
        if payload.get("working_directory") != expected_working:
            raise IntegrityError("execution working_directory is not its attested sandbox")
        for field, filename in (
            ("stdout_raw_path", "stdout.raw"),
            ("stderr_raw_path", "stderr.raw"),
        ):
            relative = payload.get(field)
            if relative != (logical_attempt / filename).as_posix():
                raise IntegrityError(f"execution {field} is not bound to its attempt")
            try:
                path = resolve_within(
                    self.project_root, self.project_root / Path(relative), must_exist=True
                )
            except OSError as error:
                raise IntegrityError(f"execution log is missing: {relative}") from error
            if (
                not path.is_file()
                or self._is_link_or_junction(path, self.project_root)
                or sha256_file(path) != payload[field.replace("_path", "_sha256")]
            ):
                raise IntegrityError(f"execution {field} content is missing or changed")
        for filename in ("stdout.txt", "stderr.txt"):
            path = attempt / filename
            if not path.is_file() or self._is_link_or_junction(path, self.project_root):
                raise IntegrityError(f"execution decoded log is missing: {filename}")

        snapshots = payload.get("source_snapshots", [])
        if not isinstance(snapshots, list):
            raise ConfigError("execution source_snapshots must be a list")
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                raise ConfigError("execution source snapshot must be an object")
            relative = snapshot.get("relative_path")
            digest = snapshot.get("sha256")
            if (
                not isinstance(relative, str)
                or "\\" in relative
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or not SHA256_PATTERN.fullmatch(str(digest))
            ):
                raise IntegrityError("execution source snapshot is malformed")
            try:
                copied = resolve_within(
                    self.project_root,
                    attempt / "sandbox" / Path(relative),
                    must_exist=True,
                )
            except OSError as error:
                raise IntegrityError(f"execution source snapshot is missing: {relative}") from error
            if (
                not copied.is_file()
                or self._is_link_or_junction(copied, self.project_root)
                or sha256_file(copied) != digest
            ):
                raise IntegrityError(f"execution source snapshot changed: {relative}")

    def _execution_events(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        starts: dict[str, list[dict[str, Any]]] = {}
        finishes: dict[str, list[dict[str, Any]]] = {}
        for event in self._registry_events():
            event_type = event.get("event_type")
            if event_type not in {"EXECUTION_STARTED", "EXECUTION_FINISHED"}:
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict) or not isinstance(payload.get("execution_id"), str):
                raise IntegrityError(f"{event_type} has no valid execution_id")
            target = starts if event_type == "EXECUTION_STARTED" else finishes
            target.setdefault(payload["execution_id"], []).append(event)
        return starts, finishes

    def start_execution(self, intent: dict[str, Any], *, stage: str) -> dict[str, Any]:
        """Commit the pre-launch execution intent before a child is started.

        An execution may only be completed through :meth:`attest_execution`.
        Keeping this transition separate makes an interrupted process visible as
        an incomplete execution instead of silently accepting a hand-written
        Registry record.
        """
        self.validate_integrity()
        if not isinstance(intent, dict):
            raise ConfigError("execution intent must be an object")
        if intent.get("run_id") != self.run_id or intent.get("stage") != stage:
            raise IntegrityError("execution intent does not belong to this stage/run")
        execution_id = self._identity("execution", intent)
        if execution_id in self._committed_identity_map():
            raise IntegrityError("execution ID already exists")
        digest = execution_intent_sha256(intent)
        starts, finishes = self._execution_events()
        if execution_id in starts or execution_id in finishes:
            raise IntegrityError("execution ID already has an attestation event")
        event = self.ledger.append(
            self.run_id,
            "EXECUTION_STARTED",
            {
                "execution_id": execution_id,
                "attempt_id": intent["attempt_id"],
                "attempt_path": intent["attempt_path"],
                "stage": stage,
                "intent_sha256": digest,
                "intent": deepcopy(intent),
            },
            stage=stage,
        )
        return event

    def attest_execution(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Commit an execution record and its FINISH event as one controlled flow."""
        kind = "execution"
        self.ledger.validate()
        if not isinstance(payload, dict):
            raise ConfigError("execution payload must be an object")
        execution_id = self._identity(kind, payload)
        if execution_id in self._committed_identity_map():
            raise IntegrityError("execution ID already exists")
        starts, finishes = self._execution_events()
        start_events = starts.get(execution_id, [])
        if len(start_events) != 1 or finishes.get(execution_id):
            raise IntegrityError("execution must have one pending START and no FINISH")
        start_payload = start_events[0].get("payload")
        if not isinstance(start_payload, dict):
            raise IntegrityError("pending START payload is invalid")
        if start_payload.get("intent_sha256") != payload.get("intent_sha256"):
            raise IntegrityError("execution payload does not match START commitment")
        intent = start_payload.get("intent")
        if not isinstance(intent, dict) or execution_intent_sha256(intent) != payload.get(
            "intent_sha256"
        ):
            raise IntegrityError("pending START intent is invalid")
        for field in EXECUTION_INTENT_FIELDS:
            if intent.get(field) != payload.get(field):
                raise IntegrityError(f"execution payload differs from START: {field}")
        self.validate_payload(kind, payload)
        self._validate_execution_files(payload)
        record = self._write_version(kind, payload)
        finish = self.ledger.append(
            self.run_id,
            "EXECUTION_FINISHED",
            {
                "execution_id": execution_id,
                "attempt_id": payload["attempt_id"],
                "attempt_path": payload["attempt_path"],
                "stage": payload["stage"],
                "status": payload["status"],
                "exit_code": payload["exit_code"],
                "stdout_raw_sha256": payload["stdout_raw_sha256"],
                "stderr_raw_sha256": payload["stderr_raw_sha256"],
                "record_sha256": record["record_sha256"],
            },
            stage=payload["stage"],
        )
        return record

    def _validate_execution_attestation(
        self,
        latest_record: dict[str, Any],
        versions: list[dict[str, Any]],
        starts: dict[str, list[dict[str, Any]]],
        finishes: dict[str, list[dict[str, Any]]],
    ) -> None:
        execution_id = latest_record["entity_id"]
        start_events = starts.get(execution_id, [])
        finish_events = finishes.get(execution_id, [])
        if len(start_events) != 1 or len(finish_events) != 1:
            raise IntegrityError(
                f"execution {execution_id} must have exactly one START and one FINISH"
            )
        start = start_events[0]
        finish = finish_events[0]
        start_payload = start.get("payload")
        finish_payload = finish.get("payload")
        if not isinstance(start_payload, dict) or not isinstance(finish_payload, dict):
            raise IntegrityError("execution attestation event payload is invalid")
        attested_hash = finish_payload.get("record_sha256")
        attested_records = [
            version for version in versions if version.get("record_sha256") == attested_hash
        ]
        if len(attested_records) != 1:
            raise IntegrityError("execution FINISH does not identify one Registry record")
        attested_record = attested_records[0]
        payload = attested_record["payload"]
        if start.get("run_id") != self.run_id or finish.get("run_id") != self.run_id:
            raise IntegrityError("execution attestation event has wrong run_id")
        if start.get("stage") != payload.get("stage") or finish.get("stage") != payload.get("stage"):
            raise IntegrityError("execution attestation stage differs from Registry")
        for event_payload in (start_payload, finish_payload):
            if event_payload.get("attempt_id") != payload.get("attempt_id"):
                raise IntegrityError("execution attestation attempt_id differs from Registry")
        if start_payload.get("stage") != payload.get("stage"):
            raise IntegrityError("EXECUTION_STARTED stage differs from Registry")
        if start_payload.get("intent_sha256") != payload.get("intent_sha256"):
            raise IntegrityError("execution intent commitment differs from START")
        intent = start_payload.get("intent")
        if not isinstance(intent, dict) or execution_intent_sha256(intent) != payload.get("intent_sha256"):
            raise IntegrityError("EXECUTION_STARTED intent is not self-consistent")
        for field in EXECUTION_INTENT_FIELDS:
            if intent.get(field) != payload.get(field):
                raise IntegrityError(f"execution intent field differs: {field}")
        if start["sequence"] >= finish["sequence"]:
            raise IntegrityError("execution FINISH precedes START")
        if finish_payload.get("status") != payload.get("status"):
            raise IntegrityError("execution FINISH status differs from attested Registry record")
        if finish_payload.get("exit_code") != payload.get("exit_code"):
            raise IntegrityError("execution FINISH exit_code differs from Registry record")
        if finish_payload.get("attempt_path") != payload.get("attempt_path"):
            raise IntegrityError("execution FINISH attempt_path differs from Registry")
        for field in ("stdout_raw_sha256", "stderr_raw_sha256"):
            if finish_payload.get(field) != payload.get(field):
                raise IntegrityError(f"execution FINISH {field} differs from Registry")
        self._validate_execution_files(payload)

    def _validate_split(self, payload: dict[str, Any], resolve_dependencies: bool) -> None:
        """M07: dataset splits are first-class immutable entities.

        A split must identify its source dataset artifact, its kind, the
        concrete selectors, a content-addressed index digest, the leakage
        boundary, the preprocessing fit scope and an immutable fingerprint.
        A free-form string can never prove which samples were isolated.
        """
        required = (
            "source_dataset_artifact_id",
            "split_kind",
            "selectors",
            "indices_sha256",
            "leakage_boundary",
            "preprocessing_fit_scope",
            "immutable_fingerprint",
        )
        missing = [field for field in required if field not in payload]
        if missing:
            raise ConfigError("split missing: " + ", ".join(missing))
        self._require_string(payload, "source_dataset_artifact_id")
        if payload["split_kind"] not in SPLIT_KINDS:
            raise ConfigError(f"invalid split_kind; must be one of {sorted(SPLIT_KINDS)}")
        if not isinstance(payload["selectors"], dict):
            raise ConfigError("split selectors must be an object")
        for field in ("indices_sha256", "immutable_fingerprint"):
            value = payload[field]
            if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
                raise ConfigError(f"split {field} must be a SHA-256 digest")
        if not isinstance(payload["leakage_boundary"], dict):
            raise ConfigError("split leakage_boundary must be an object")
        if payload["preprocessing_fit_scope"] not in PREPROCESSING_FIT_SCOPES:
            raise ConfigError(
                f"split preprocessing_fit_scope must be one of "
                f"{sorted(PREPROCESSING_FIT_SCOPES)}"
            )
        if not resolve_dependencies:
            return
        source = self.latest("artifact", payload["source_dataset_artifact_id"])[
            "payload"
        ]
        if source.get("status") != "VALID":
            raise IntegrityError("split source dataset artifact is not valid")

    def _validate_result(self, payload: dict[str, Any], resolve_dependencies: bool) -> None:
        required = (
            "artifact_id",
            "execution_id",
            "question_id",
            "model_id",
            "result_kind",
            "metric",
            "value",
            "unit",
            "direction",
            "scenario",
            "dataset_split_id",
            "sample_size",
            "source_locator",
            "display",
        )
        missing = [field for field in required if field not in payload]
        if missing:
            raise ConfigError("result missing: " + ", ".join(missing))
        for field in (
            "artifact_id",
            "execution_id",
            "question_id",
            "model_id",
            "result_kind",
            "metric",
            "unit",
            "scenario",
            "dataset_split_id",
        ):
            self._require_string(payload, field)
        if payload["direction"] not in DIRECTIONS:
            raise ConfigError("invalid metric direction")
        if payload["result_kind"] not in RESULT_KINDS:
            raise ConfigError(
                f"invalid result_kind; must be one of {sorted(RESULT_KINDS)}"
            )
        if isinstance(payload["value"], bool) or not isinstance(
            payload["value"], (int, float, str)
        ):
            raise ConfigError("result value must be a finite decimal-compatible scalar")
        try:
            numeric_value = Decimal(str(payload["value"]))
        except (InvalidOperation, ValueError) as error:
            raise ConfigError("result value is not decimal-compatible") from error
        if not numeric_value.is_finite():
            raise ConfigError("result value must be finite")
        if not isinstance(payload["sample_size"], int) or isinstance(
            payload["sample_size"], bool
        ) or payload["sample_size"] <= 0:
            raise ConfigError("sample_size must be a positive integer")
        locator = payload["source_locator"]
        if not isinstance(locator, dict) or not isinstance(locator.get("format"), str):
            raise ConfigError("source_locator must identify a structured location")
        if locator.get("format") != "json_pointer":
            raise ConfigError(
                "unsupported source_locator format; v1 requires json_pointer"
            )
        pointer = locator.get("pointer")
        if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
            raise ConfigError("json_pointer locator requires a valid pointer")
        display = payload["display"]
        if not isinstance(display, dict) or display.get("rounding") != "half_even":
            raise ConfigError("only half_even display rounding is supported")
        decimals = display.get("decimals")
        if not isinstance(decimals, int) or isinstance(decimals, bool) or not 0 <= decimals <= 12:
            raise ConfigError("display decimals out of range")
        quantum = Decimal(1).scaleb(-decimals)
        rendered = str(numeric_value.quantize(quantum, rounding=ROUND_HALF_EVEN))
        if display.get("rendered") != rendered:
            raise ConfigError(f"rendered value must be {rendered}")
        uncertainty = payload.get("uncertainty")
        if uncertainty is not None:
            if not isinstance(uncertainty, dict):
                raise ConfigError("uncertainty must be an object")
            for key in ("lower", "upper"):
                if key in uncertainty and not Decimal(str(uncertainty[key])).is_finite():
                    raise ConfigError("uncertainty bound must be finite")
        if not resolve_dependencies:
            return
        artifact = self.latest("artifact", payload["artifact_id"])["payload"]
        execution = self.latest("execution", payload["execution_id"])["payload"]
        if artifact.get("status") != "VALID" or artifact.get("artifact_class") != "production":
            raise UntrustedArtifactError("result source is not a valid production artifact")
        if execution.get("status") != "VALID" or execution.get("artifact_class") != "production":
            raise UntrustedArtifactError("result execution is not valid production")
        if artifact.get("execution_id") != payload["execution_id"]:
            raise IntegrityError("result artifact and execution differ")
        if payload["dataset_split_id"] not in execution.get("dataset_split_ids", []):
            raise IntegrityError("result split was not declared by its execution")
        split = self.latest("split", payload["dataset_split_id"])["payload"]
        if split.get("status") != "VALID":
            raise IntegrityError(f"result split is not a current valid split: {payload['dataset_split_id']}")

    def _validate_claim(self, payload: dict[str, Any], resolve_dependencies: bool) -> None:
        required = (
            "claim_type",
            "statement",
            "supports",
            "counterevidence",
            "scope",
            "strength",
        )
        missing = [field for field in required if field not in payload]
        if missing:
            raise ConfigError("claim missing: " + ", ".join(missing))
        if payload["claim_type"] not in CLAIM_TYPES:
            raise ConfigError("invalid claim_type")
        if payload["strength"] not in CLAIM_STRENGTHS:
            raise ConfigError("invalid claim strength")
        if payload.get("counterevidence") and payload["strength"] == "confirmed":
            raise IntegrityError(
                "a confirmed claim cannot coexist with unresolved counterevidence; "
                "downgrade the strength or resolve the counterevidence"
            )
        self._require_string(payload, "statement")
        self._require_string(payload, "scope")
        supports = self._require_string_list(payload, "supports")
        self._require_string_list(payload, "counterevidence")
        if payload["claim_type"] != "limitation" and not supports:
            raise ConfigError("non-limitation claim requires support")
        if not resolve_dependencies:
            return
        # claim-policy-v2: claim types must be backed by matching entity kinds,
        # so a claim's strength cannot ride on unrelated support.
        support_kinds = {
            self.find_entity(support_id)["entity_kind"] for support_id in supports
        }
        if payload["claim_type"] == "computed" and not (
            support_kinds & {"result", "formula"}
        ):
            raise IntegrityError(
                "computed claim requires Result or Formula support"
            )
        if payload["claim_type"] == "observational" and not (
            support_kinds & {"result", "evidence"}
        ):
            raise IntegrityError(
                "observational claim requires Result or evidence support"
            )
        if payload["claim_type"] == "theoretical" and "formula" not in support_kinds:
            raise IntegrityError("theoretical claim requires Formula support")
        for support_id in supports:
            support = self.find_entity(support_id)
            support_payload = support["payload"]
            if support_payload.get("status") != "VALID":
                raise IntegrityError(f"claim support is not valid: {support_id}")
            if support["entity_kind"] == "artifact" and support_payload.get(
                "artifact_class"
            ) in INELIGIBLE_FINAL_CLASSES:
                raise UntrustedArtifactError(
                    f"claim cannot use {support_payload['artifact_class']} support"
                )
            if support["entity_kind"] == "result":
                artifact = self.latest("artifact", support_payload["artifact_id"])["payload"]
                if artifact.get("artifact_class") in INELIGIBLE_FINAL_CLASSES:
                    raise UntrustedArtifactError("claim result descends from ineligible artifact")
        for counter_id in payload["counterevidence"]:
            counter = self.find_entity(counter_id)
            if counter["payload"].get("status") != "VALID":
                raise IntegrityError(f"claim counterevidence is invalid: {counter_id}")

    def _validate_other(self, kind: str, payload: dict[str, Any], resolve_dependencies: bool) -> None:
        if kind == "formula":
            formula_type = payload.get("formula_type")
            if formula_type not in FORMULA_TYPES:
                raise ConfigError(
                    f"invalid formula_type; must be one of {sorted(FORMULA_TYPES)}"
                )
            dependencies = self._require_string_list(payload, "dependencies")
            self._require_string_list(payload, "citations")
            if not isinstance(payload.get("display_values", []), list):
                raise ConfigError("formula display_values must be a list")
            # formula-v1: a formula is not a display string; it must carry its
            # expression, symbol table, premises, derivation and boundary cases.
            self._require_string(payload, "expression")
            symbols = payload.get("symbols")
            if not isinstance(symbols, list) or not symbols or not all(
                isinstance(item, dict) and item.get("name") for item in symbols
            ):
                raise ConfigError("formula symbols must be a non-empty list of named objects")
            for field in ("premises", "derivation", "boundary_cases"):
                value = payload.get(field)
                if not isinstance(value, list) or not all(
                    isinstance(item, str) and item for item in value
                ):
                    raise ConfigError(f"formula {field} must be a list of strings")
            if formula_type == "theoretical":
                if not payload.get("theorem_conditions") or not payload.get(
                    "derivation"
                ):
                    raise ConfigError(
                        "theoretical formula requires theorem_conditions and derivation"
                    )
            elif formula_type == "empirical":
                if not isinstance(payload.get("data_basis"), dict) or not payload.get(
                    "fitting_evidence"
                ):
                    raise ConfigError(
                        "empirical formula requires a data_basis object and fitting_evidence"
                    )
            elif formula_type == "optimization":
                if not isinstance(payload.get("objective"), str) or not isinstance(
                    payload.get("constraints"), list
                ):
                    raise ConfigError(
                        "optimization formula requires an objective string and constraints list"
                    )
            elif formula_type == "statistical":
                if not payload.get("assumptions") or not payload.get("uncertainty"):
                    raise ConfigError(
                        "statistical formula requires assumptions and uncertainty"
                    )
            dependency_ids = dependencies + payload["citations"]
        elif kind == "figure":
            required_contract = (
                "question_id",
                "role",
                "necessity",
                "backend",
                "generator_artifact_id",
                "input_artifact_ids",
                "units",
                "uncertainty_description",
                "information_gain",
                "paper_locator",
                "rendering_audit_id",
            )
            missing_contract = [field for field in required_contract if field not in payload]
            legacy_sidecar = False
            if missing_contract:
                # Existing v1 records remain readable for integrity audits. A
                # legacy sidecar is explicitly non-production and cannot pass
                # the new semantic gate, but older fixtures need not be
                # rewritten merely to load the registry.
                sidecar_probe = None
                try:
                    sidecar_record = self.latest("artifact", payload.get("sidecar_artifact_id", ""))["payload"]
                    sidecar_path = resolve_within(
                        self.project_root,
                        self.project_root / sidecar_record["relative_path"],
                        must_exist=True,
                    )
                    sidecar_probe = json.loads(sidecar_path.read_text("utf-8"))
                    legacy_sidecar = sidecar_probe.get("schema") == "mmflow-figure-sidecar/v1"
                except (IntegrityError, OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
                    legacy_sidecar = False
                if not legacy_sidecar:
                    # Preserve the integrity-error classification for a
                    # malformed or tampered sidecar.  The old v1 tests and
                    # callers rely on this distinction when triaging data
                    # corruption versus a missing production field.
                    sidecar_schema = (
                        sidecar_probe.get("schema") if isinstance(sidecar_probe, dict) else None
                    )
                    # A v2 sidecar proves that this is a production figure
                    # attempt, so report the missing Registry contract field
                    # directly.  Only an actually malformed/unknown schema
                    # is an integrity classification.
                    if sidecar_schema == "mmflow-figure-sidecar/v2":
                        raise ConfigError(
                            "figure production contract missing: "
                            + ", ".join(missing_contract)
                        )
                    if sidecar_schema is not None:
                        raise IntegrityError("figure sidecar does not use the fixed schema")
                    raise ConfigError("figure production contract missing: " + ", ".join(missing_contract))
            if not legacy_sidecar:
                for field in (
                    "question_id",
                    "role",
                    "necessity",
                    "backend",
                    "generator_artifact_id",
                    "uncertainty_description",
                    "information_gain",
                    "paper_locator",
                    "rendering_audit_id",
                ):
                    self._require_string(payload, field)
            if not legacy_sidecar and payload["necessity"] not in {"required", "optional"}:
                raise ConfigError("figure necessity must be required or optional")
            if not legacy_sidecar and payload["backend"] not in {"python", "matlab"}:
                raise ConfigError("figure backend must be python or matlab")
            input_ids = payload.get("input_artifact_ids", [])
            if not legacy_sidecar and (not isinstance(input_ids, list) or not all(isinstance(item, str) and item for item in input_ids)):
                raise ConfigError("figure input_artifact_ids must be a list of IDs")
            if not legacy_sidecar and (not isinstance(payload["units"], dict) or not payload["units"]):
                raise ConfigError("figure units must be a non-empty object")
            self._require_string(payload, "artifact_id")
            source_results = self._require_string_list(payload, "source_results")
            caption_claims = self._require_string_list(payload, "caption_claims")
            self._require_string(payload, "sidecar_artifact_id")
            dependency_ids = [
                payload["artifact_id"],
                payload["sidecar_artifact_id"],
                *source_results,
                *caption_claims,
            ]
            if resolve_dependencies:
                self._validate_figure_sidecar_lock(payload, allow_legacy=legacy_sidecar)
        elif kind == "citation":
            for field in (
                "title",
                "source_url",
                "access_level",
                "verified_at",
                "verification_status",
                "source_role",
                "version",
            ):
                self._require_string(payload, field)
            authors = self._require_string_list(payload, "authors")
            if not authors:
                raise ConfigError("citation requires at least one author")
            year = payload.get("year")
            if isinstance(year, bool) or not isinstance(year, (str, int)) or not str(year).strip():
                raise ConfigError("citation requires a valid year")
            if payload["access_level"] not in CITATION_ACCESS_LEVELS:
                raise ConfigError(
                    f"invalid citation access_level; must be one of "
                    f"{sorted(CITATION_ACCESS_LEVELS)}"
                )
            if payload["verification_status"] not in CITATION_VERIFICATION_STATUSES:
                raise ConfigError(
                    f"invalid citation verification_status; must be one of "
                    f"{sorted(CITATION_VERIFICATION_STATUSES)}"
                )
            if payload["source_role"] not in CITATION_SOURCE_ROLES:
                raise ConfigError(
                    f"invalid citation source_role; must be one of "
                    f"{sorted(CITATION_SOURCE_ROLES)}"
                )
            if not isinstance(payload["metadata_verification"], dict):
                raise ConfigError("citation metadata_verification must be an object")
            locator = payload.get("source_locator")
            if locator is not None and not isinstance(locator, dict):
                raise ConfigError("citation source_locator must be an object")
            support = payload.get("content_support_verification")
            if support is not None and not isinstance(support, (str, dict)):
                raise ConfigError("citation content_support_verification must be a string or object")
            dependency_ids = list(payload.get("supports_claims", []))
        elif kind == "finding":
            for field in ("severity", "finding_status", "statement"):
                self._require_string(payload, field)
            evidence = self._require_string_list(payload, "evidence")
            affected = self._require_string_list(payload, "affected_claims")
            self._require_string_list(payload, "affected_entities")
            rerun_scope = self._require_string_list(payload, "rerun_scope")
            if not rerun_scope or not all(
                re.fullmatch(r"P(?:1[01]|[0-9])", item) for item in rerun_scope
            ):
                raise ConfigError("finding rerun_scope must list valid P stages")
            if payload["severity"] not in {"CRITICAL", "MAJOR", "MODERATE", "MINOR"}:
                raise ConfigError("invalid finding severity")
            if payload["finding_status"] not in {"OPEN", "CLOSED", "ACCEPTED_LIMITATION"}:
                raise ConfigError("invalid finding status")
            if payload["finding_status"] == "ACCEPTED_LIMITATION" and payload["severity"] in {
                "CRITICAL",
                "MAJOR",
            }:
                raise IntegrityError("critical or major finding cannot be accepted as a limitation")
            closure = payload.get("closure_evidence", [])
            if payload["finding_status"] == "CLOSED" and not closure:
                raise ConfigError("closed finding requires closure evidence")
            if not isinstance(closure, list):
                raise ConfigError("closure_evidence must be a list")
            if payload["finding_status"] == "CLOSED" and not isinstance(
                payload.get("finding_closure"), dict
            ):
                raise ConfigError("closed finding requires a structured finding_closure")
            dependency_ids = evidence + affected + list(closure)
        elif kind == "evidence":
            self._require_string(payload, "evidence_type")
            if not isinstance(payload.get("content"), dict):
                raise ConfigError("evidence content must be an object")
            dependency_ids = self._require_string_list(payload, "supports")
            policy_path = Path(__file__).with_name("policies") / "schemas-v1.json"
            if policy_path.is_file():
                try:
                    contracts = json.loads(policy_path.read_text("utf-8"))["evidence_contracts"]
                except (OSError, UnicodeError, json.JSONDecodeError, KeyError) as error:
                    raise IntegrityError("cannot load evidence schema policy") from error
                required = contracts.get(payload["evidence_type"])
                if not isinstance(required, list):
                    raise ConfigError(f"unknown evidence_type: {payload['evidence_type']}")
                missing = [field for field in required if field not in payload["content"]]
                if missing:
                    raise ConfigError("evidence content missing: " + ", ".join(missing))
        else:
            raise ConfigError(f"unsupported registry kind: {kind}")
        if resolve_dependencies:
            for entity_id in dependency_ids:
                dependency = self.find_entity(entity_id)
                if dependency["payload"].get("status") != "VALID":
                    raise IntegrityError(f"dependency is not valid: {entity_id}")

    def _validate_figure_sidecar_lock(
        self, payload: dict[str, Any], *, allow_legacy: bool = False
    ) -> None:
        """Lock the image and its sidecar to the same production execution.

        The image artifact and the sidecar artifact must both be production
        outputs of the same execution, the sidecar must use the fixed schema,
        its recorded image SHA-256 must match the live image file, and its
        source-result IDs must equal the Figure Registry's declared results.
        This prevents "the figure exists and the data exists, but they were
        not produced by the same run".
        """
        image = self.latest("artifact", payload["artifact_id"])["payload"]
        sidecar = self.latest("artifact", payload["sidecar_artifact_id"])["payload"]
        if image.get("status") != "VALID" or image.get("artifact_class") != "production":
            raise UntrustedArtifactError("figure image must be a current production artifact")
        if (
            sidecar.get("status") != "VALID"
            or sidecar.get("artifact_class") != "production"
        ):
            raise UntrustedArtifactError("figure sidecar must be a current production artifact")
        image_execution = image.get("execution_id")
        sidecar_execution = sidecar.get("execution_id")
        if not isinstance(image_execution, str) or image_execution != sidecar_execution:
            raise IntegrityError(
                "figure image and sidecar must come from the same execution"
            )
        execution = self.latest("execution", image_execution)["payload"]
        if execution.get("status") != "VALID" or execution.get("exit_code") != 0:
            raise IntegrityError("figure producer execution is not valid")
        try:
            image_path = resolve_within(
                self.project_root,
                self.project_root / image["relative_path"],
                must_exist=True,
            )
            sidecar_path = resolve_within(
                self.project_root,
                self.project_root / sidecar["relative_path"],
                must_exist=True,
            )
        except OSError as error:
            raise IntegrityError("figure image or sidecar file is missing") from error
        if sha256_file(image_path) != image["sha256"]:
            raise IntegrityError("figure image changed after artifact registration")
        try:
            sidecar_value = json.loads(sidecar_path.read_text("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise IntegrityError("figure sidecar is not valid JSON") from error
        if not isinstance(sidecar_value, dict):
            raise IntegrityError("figure sidecar must be a JSON object")
        schema = sidecar_value.get("schema")
        if schema not in {"mmflow-figure-sidecar/v1", "mmflow-figure-sidecar/v2"}:
            raise IntegrityError("figure sidecar does not use the fixed schema")
        if schema == "mmflow-figure-sidecar/v1" and not allow_legacy:
            raise UntrustedArtifactError(
                "legacy v1 figure sidecars are readable but cannot be production evidence"
            )
        if sidecar_value.get("image_sha256") != image["sha256"]:
            raise IntegrityError("figure sidecar image hash differs from the image artifact")
        if sha256_file(sidecar_path) != sidecar.get("sha256"):
            raise IntegrityError("figure sidecar changed after artifact registration")
        if sidecar.get("size_bytes") != sidecar_path.stat().st_size:
            raise IntegrityError("figure sidecar size differs from the registered artifact")
        if sidecar_value.get("execution_id") != image_execution:
            raise IntegrityError("figure sidecar execution differs from the image execution")
        sidecar_results = sidecar_value.get("source_result_ids")
        if not isinstance(sidecar_results, list) or set(sidecar_results) != set(
            payload["source_results"]
        ):
            raise IntegrityError(
                "figure sidecar result set differs from the Figure Registry"
            )
        for field in (
            "question_id",
            "role",
            "backend",
            "generator_artifact_id",
            "input_artifact_ids",
            "units",
            "uncertainty_description",
            "information_gain",
            "paper_locator",
            "rendering_audit_id",
        ):
            if not allow_legacy and sidecar_value.get(field) != payload.get(field):
                raise IntegrityError(f"figure sidecar {field} differs from registry contract")
        if not allow_legacy:
            generator = self.latest("artifact", payload["generator_artifact_id"])["payload"]
            if generator.get("status") != "VALID" or generator.get("artifact_class") in INELIGIBLE_FINAL_CLASSES:
                raise UntrustedArtifactError("figure generator is not production-eligible")
            for input_id in payload["input_artifact_ids"]:
                input_artifact = self.latest("artifact", input_id)["payload"]
                if input_artifact.get("status") != "VALID" or input_artifact.get("artifact_class") in INELIGIBLE_FINAL_CLASSES:
                    raise UntrustedArtifactError("figure input artifact is not production-eligible")
        for result_id in payload["source_results"]:
            result = self.latest("result", result_id)["payload"]
            if result.get("status") != "VALID":
                raise IntegrityError(f"figure source result is not valid: {result_id}")
            if not allow_legacy and result.get("question_id") != payload.get("question_id"):
                raise IntegrityError(
                    "figure source result question_id differs from the Figure Registry question_id: "
                    + result_id
                )
            result_artifact = self.latest("artifact", result["artifact_id"])["payload"]
            if result_artifact.get("artifact_class") not in INELIGIBLE_FINAL_CLASSES:
                continue
            raise UntrustedArtifactError(
                f"figure source result descends from an ineligible artifact: {result_id}"
            )

    def validate_payload(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        resolve_dependencies: bool = True,
    ) -> None:
        kind = self.normalize_kind(kind)
        if not isinstance(payload, dict):
            raise ConfigError("registry payload must be an object")
        self._identity(kind, payload)
        if payload.get("run_id") != self.run_id:
            raise IntegrityError("registry payload belongs to another run_id")
        if payload.get("status") not in ENTITY_STATUSES:
            raise ConfigError("invalid entity status")
        if kind == "artifact":
            self._validate_artifact(payload, resolve_dependencies)
        elif kind == "execution":
            self._validate_execution(payload, resolve_dependencies)
        elif kind == "result":
            self._validate_result(payload, resolve_dependencies)
        elif kind == "claim":
            self._validate_claim(payload, resolve_dependencies)
        elif kind == "split":
            self._validate_split(payload, resolve_dependencies)
        else:
            self._validate_other(kind, payload, resolve_dependencies)

    def _entity_dir(self, kind: str, entity_id: str) -> Path:
        kind = self.normalize_kind(kind)
        return self.root / KIND_DIRECTORIES[kind] / entity_id

    def _committed_versions(self, kind: str, entity_id: str) -> list[dict[str, Any]]:
        kind = self.normalize_kind(kind)
        head_key = self.ledger.head()["head_sha256"]
        if self._version_cache_head != head_key:
            self._version_cache_head = head_key
            self._version_cache = {}
        cache_key = (kind, entity_id)
        cached = self._version_cache.get(cache_key)
        if cached is not None:
            # Freshness gate: a cached entry is only reused when every record
            # file still has its original size+mtime_ns.  Any content edit
            # changes the stat signature, forcing a full re-read and hash
            # re-verification, so read-time tamper detection is preserved.
            records, signatures = cached
            fresh = True
            for relative, signature in signatures:
                try:
                    stat = (self.project_root / relative).stat()
                except OSError:
                    fresh = False
                    break
                if (stat.st_size, stat.st_mtime_ns) != signature:
                    fresh = False
                    break
            if fresh:
                return deepcopy(records)
        records: list[dict[str, Any]] = []
        signatures: list[tuple[str, tuple[int, int]]] = []
        for event in self._registry_events():
            if event["event_type"] != "REGISTRY_RECORDED":
                continue
            event_payload = event["payload"]
            if event_payload.get("kind") != kind or event_payload.get("entity_id") != entity_id:
                continue
            expected_version = len(records) + 1
            if event_payload.get("entity_version") != expected_version:
                raise IntegrityError("registry event version is not continuous")
            path = resolve_within(
                self.project_root,
                self.project_root / Path(str(event_payload.get("record_path"))),
                must_exist=True,
            )
            if not path.is_file():
                raise IntegrityError("committed registry record is missing")
            try:
                record = json.loads(path.read_text("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise IntegrityError("registry record is not valid JSON") from error
            digest = sha256_bytes(
                canonical_json_bytes(
                    {key: value for key, value in record.items() if key != "record_sha256"}
                )
            )
            if digest != record.get("record_sha256") or digest != event_payload.get(
                "record_sha256"
            ):
                raise IntegrityError("registry record hash mismatch")
            if path.name != f"{expected_version:06d}_{digest}.json":
                raise IntegrityError("registry filename or version mismatch")
            if (
                record.get("entity_kind") != kind
                or record.get("entity_id") != entity_id
                or record.get("entity_version") != expected_version
                or record.get("run_id") != self.run_id
            ):
                raise IntegrityError("registry record identity mismatch")
            records.append(record)
            try:
                stat = path.stat()
                signatures.append(
                    (path.relative_to(self.project_root).as_posix(),
                     (stat.st_size, stat.st_mtime_ns))
                )
            except OSError:
                signatures.append(("", (-1, -1)))
        self._version_cache[cache_key] = (deepcopy(records), list(signatures))
        return records

    def _committed_identity_map(self) -> dict[str, str]:
        identities: dict[str, str] = {}
        for event in self._registry_events():
            if event["event_type"] != "REGISTRY_RECORDED":
                continue
            kind = self.normalize_kind(str(event["payload"].get("kind")))
            entity_id = str(event["payload"].get("entity_id"))
            previous = identities.setdefault(entity_id, kind)
            if previous != kind:
                raise IntegrityError(f"entity ID is used by two kinds: {entity_id}")
        return identities

    def _recover_journal(self) -> None:
        """Complete or abort a crashed Registry write from its journal.

        A write is two-phase: the record file is staged, then the
        REGISTRY_RECORDED event is appended.  If the ledger already contains
        the event for this record the write committed and only the journal
        must be removed; otherwise the staged record file is deleted as an
        aborted write.  Recovery never guesses: both outcomes are decided by
        the immutable ledger.
        """
        if not self.journal_path.exists():
            return
        try:
            journal = json.loads(self.journal_path.read_text("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise IntegrityError("registry journal is corrupt; manual review required") from error
        if not isinstance(journal, dict):
            raise IntegrityError("registry journal is not an object")
        record_sha256 = journal.get("record_sha256")
        record_path = journal.get("record_path")
        if not isinstance(record_sha256, str) or not isinstance(record_path, str):
            raise IntegrityError("registry journal identity is invalid")
        committed = False
        for event in self._registry_events():
            if event.get("event_type") != "REGISTRY_RECORDED":
                continue
            event_payload = event.get("payload")
            if (
                isinstance(event_payload, dict)
                and event_payload.get("record_sha256") == record_sha256
                and event_payload.get("record_path") == record_path
            ):
                committed = True
                break
        staged = self.project_root / record_path
        if not committed:
            try:
                if staged.is_file() and not self._is_link_or_junction(staged, self.project_root):
                    staged.unlink()
            except OSError:
                raise IntegrityError("cannot remove aborted registry record") from None
        self.journal_path.unlink()

    def _write_version(
        self, kind: str, payload: dict[str, Any], stage: str | None = None
    ) -> dict[str, Any]:
        kind = self.normalize_kind(kind)
        entity_id = self._identity(kind, payload)
        versions = self._committed_versions(kind, entity_id)
        version = len(versions) + 1
        # Under the project single-writer lock the next ledger sequence is
        # deterministic; record it so gates and finding closure can order
        # entities against events without extra I/O.
        sequence = int(self.ledger.head()["sequence"]) + 1
        epoch = self._resolve_epoch(stage)
        record: dict[str, Any] = {
            "registry_version": 2,
            "entity_kind": kind,
            "entity_id": entity_id,
            "entity_version": version,
            "run_id": self.run_id,
            "created_stage": stage,
            "stage_epoch": epoch,
            "created_ledger_sequence": sequence,
            "payload": deepcopy(payload),
        }
        record["record_sha256"] = sha256_bytes(canonical_json_bytes(record))
        path = self._entity_dir(kind, entity_id) / (
            f"{version:06d}_{record['record_sha256']}.json"
        )
        relative = path.relative_to(self.project_root).as_posix()
        journal = {
            "journal_version": 1,
            "kind": kind,
            "entity_id": entity_id,
            "entity_version": version,
            "record_path": relative,
            "record_sha256": record["record_sha256"],
            "phase": "PREPARED",
        }
        atomic_write_json(self.journal_path, journal)
        atomic_write_json(path, record)
        event = self.ledger.append(
            self.run_id,
            "REGISTRY_RECORDED",
            {
                "kind": kind,
                "entity_id": entity_id,
                "entity_version": version,
                "record_path": relative,
                "record_sha256": record["record_sha256"],
            },
        )
        if int(event["sequence"]) != sequence:
            raise IntegrityError("registry write sequence changed under the writer")
        journal["phase"] = "COMMITTED"
        atomic_write_json(self.journal_path, journal)
        self.journal_path.unlink()
        return deepcopy(record)

    STAGE_BOUND_KINDS = {
        "result",
        "claim",
        "formula",
        "figure",
        "finding",
        "evidence",
        "split",
    }

    def _check_stage_eligibility(self, kind: str, payload: dict[str, Any], stage: str | None) -> None:
        if kind in self.STAGE_BOUND_KINDS:
            if stage is None:
                raise IntegrityError(
                    f"{kind} registration requires an active workflow stage"
                )
            if kind == "evidence":
                allowed = self.evidence_stage_matrix.get(str(payload.get("evidence_type")), [])
                if allowed and stage not in allowed:
                    raise IntegrityError(
                        f"evidence type {payload.get('evidence_type')} may not be "
                        f"registered during {stage}; allowed stages: {sorted(allowed)}"
                    )

    def _extract_dependency_ids(self, content: dict[str, Any], paths: list[str]) -> set[str]:
        """Deterministically extract entity IDs from evidence content.

        Every ID referenced inside ``content`` at a declared path must also be
        declared in the explicit ``supports`` list.  The extraction is the
        canonical dependency source, so a caller cannot sneak an undeclared
        reference past lineage propagation.
        """
        extracted: set[str] = set()

        def resolve(current: Any, path_parts: list[str]) -> list[Any]:
            if not path_parts:
                return [current] if isinstance(current, (str, list)) else []
            part = path_parts[0]
            if part == "[]":
                if not isinstance(current, list):
                    return []
                found: list[Any] = []
                for item in current:
                    found.extend(resolve(item, path_parts[1:]))
                return found
            if isinstance(current, dict) and part in current:
                return resolve(current[part], path_parts[1:])
            if isinstance(current, list):
                found = []
                for item in current:
                    found.extend(resolve(item, path_parts))
                return found
            return []

        def normalize(raw: str) -> list[str]:
            raw = raw.replace("\\[", "[]")
            parts = raw.split(".")
            output: list[str] = []
            for part in parts:
                if part.endswith("[]"):
                    output.append(part[:-2])
                    output.append("[]")
                elif part:
                    output.append(part)
            return output

        for path in paths:
            for value in resolve(content, normalize(path)):
                if isinstance(value, str) and value:
                    extracted.add(value)
                elif isinstance(value, list):
                    extracted.update(item for item in value if isinstance(item, str) and item)
        return extracted

    def _validate_evidence_dependencies(self, payload: dict[str, Any]) -> None:
        evidence_type = payload.get("evidence_type")
        policy_path = Path(__file__).with_name("policies") / "schemas-v1.json"
        if not policy_path.is_file():
            raise IntegrityError("cannot load evidence dependency policy")
        try:
            contracts = json.loads(policy_path.read_text("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise IntegrityError("cannot load evidence dependency policy") from error
        dependency_fields = contracts.get("evidence_dependency_fields", {})
        paths = dependency_fields.get(evidence_type, [])
        if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
            raise IntegrityError(f"evidence dependency policy is invalid for {evidence_type}")
        content = payload.get("content")
        if not isinstance(content, dict):
            raise IntegrityError("evidence content must be an object")
        extracted = self._extract_dependency_ids(content, paths)
        supports = set(payload.get("supports", []))
        if extracted != supports:
            raise IntegrityError(
                f"evidence {payload.get('evidence_id')} dependency mismatch: "
                f"declared supports={sorted(supports)} extracted={sorted(extracted)}"
            )

    def register(
        self, kind: str, payload: dict[str, Any], *, stage: str | None = None
    ) -> dict[str, Any]:
        kind = self.normalize_kind(kind)
        if kind == "execution":
            raise IntegrityError(
                "execution records require ExecutionRunner.start_execution/attest_execution"
            )
        self._recover_journal()
        self.validate_integrity(deep=False)
        entity_id = self._identity(kind, payload)
        identities = self._committed_identity_map()
        if entity_id in identities:
            if identities[entity_id] != kind:
                raise IntegrityError("entity ID is globally unique across registry kinds")
            original = self.latest(kind, entity_id)["payload"]
            if kind == "artifact" and original.get("artifact_class") != payload.get(
                "artifact_class"
            ):
                raise IntegrityError("artifact class is immutable")
            raise IntegrityError("entity already exists; use a new ID or status revision")
        self._check_stage_eligibility(kind, payload, stage)
        self.validate_payload(kind, payload)
        if kind == "evidence":
            self._validate_evidence_dependencies(payload)
        return self._write_version(kind, payload, stage=stage)

    def latest(self, kind: str, entity_id: str) -> dict[str, Any]:
        kind = self.normalize_kind(kind)
        if not ID_PATTERN.fullmatch(entity_id):
            raise ConfigError("invalid entity ID")
        self._recover_journal()
        versions = self._committed_versions(kind, entity_id)
        if not versions:
            raise IntegrityError(f"unknown {kind}: {entity_id}")
        return deepcopy(versions[-1])

    def find_entity(self, entity_id: str) -> dict[str, Any]:
        if not ID_PATTERN.fullmatch(entity_id):
            raise ConfigError("invalid entity ID")
        self._recover_journal()
        kind = self._committed_identity_map().get(entity_id)
        if kind is None:
            raise IntegrityError(f"unknown registry entity: {entity_id}")
        return self.latest(kind, entity_id)

    def revise_status(
        self,
        kind: str,
        entity_id: str,
        status: str,
        reason: str,
    ) -> dict[str, Any]:
        kind = self.normalize_kind(kind)
        if status not in ENTITY_STATUSES or not reason.strip():
            raise ConfigError("status revision requires valid status and reason")
        self._recover_journal()
        self.validate_integrity(deep=False)
        latest = self.latest(kind, entity_id)
        current_status = latest["payload"].get("status")
        if kind == "finding":
            raise IntegrityError(
                "finding lifecycle cannot be changed by generic status revision; use close_finding"
            )
        if STATUS_RANK.get(status, -1) <= STATUS_RANK.get(current_status, -1):
            raise IntegrityError(
                f"status revision must be monotonic: {current_status} -> {status}"
            )
        payload = deepcopy(latest["payload"])
        payload["status"] = status
        payload["status_reason"] = reason.strip()
        self.validate_payload(kind, payload, resolve_dependencies=False)
        return self._write_version(
            kind, payload, stage=latest.get("created_stage")
        )

    def close_finding(
        self,
        finding_id: str,
        closure: dict[str, Any],
        reason: str,
        *,
        mode: str = "CLOSED",
    ) -> dict[str, Any]:
        """Close a finding only through a fully verified closure contract.

        A closure evidence is accepted only when it references this finding,
        was created after the finding, and is backed by re-run gates that
        passed after the finding with report hashes matching the ledger.
        A generic current-valid evidence can no longer close a finding.
        """
        if mode not in {"CLOSED", "ACCEPTED_LIMITATION"}:
            raise ConfigError("invalid finding closure mode")
        if not isinstance(closure, dict) or not closure:
            raise ConfigError("finding closure must be a structured object")
        if not isinstance(reason, str) or not reason.strip():
            raise ConfigError("finding closure requires a non-empty reason")
        if closure.get("finding_id") != finding_id:
            raise IntegrityError("closure contract names a different finding")
        self._recover_journal()
        self.validate_integrity(deep=False)
        latest = self.latest("finding", finding_id)
        original = latest["payload"]
        finding_created_sequence = int(latest.get("created_ledger_sequence", 0))
        if original.get("status") != "VALID" or original.get("finding_status") != "OPEN":
            raise IntegrityError("only a current open finding can be closed")
        if mode == "ACCEPTED_LIMITATION" and original.get("severity") in {"CRITICAL", "MAJOR"}:
            raise IntegrityError("critical or major finding must be fixed, not accepted")

        closure_evidence = closure.get("closure_evidence_ids", [])
        if not isinstance(closure_evidence, list) or not closure_evidence:
            raise ConfigError("finding closure requires non-empty evidence")
        if len(closure_evidence) != len(set(closure_evidence)):
            raise IntegrityError("finding closure evidence IDs must be unique")
        for evidence_id in closure_evidence:
            evidence = self.find_entity(evidence_id)
            evidence_payload = evidence["payload"]
            if evidence["entity_kind"] != "evidence" or evidence_payload.get(
                "status"
            ) != "VALID":
                raise IntegrityError(f"closure evidence is not current and valid: {evidence_id}")
            if int(evidence.get("created_ledger_sequence", 0)) <= finding_created_sequence:
                raise IntegrityError(
                    f"closure evidence predates the finding: {evidence_id}"
                )
            references_finding = finding_id in evidence_payload.get("supports", [])
            content = evidence_payload.get("content")
            if isinstance(content, dict) and content.get("finding_id") == finding_id:
                references_finding = True
            if not references_finding:
                raise IntegrityError(
                    f"closure evidence does not reference the finding: {evidence_id}"
                )

        affected = set(original.get("affected_claims", [])) | set(
            original.get("affected_entities", [])
        )
        declared_affected = set(closure.get("affected_entities", []))
        if declared_affected != affected:
            raise IntegrityError(
                "closure affected-entity set differs from the finding's registry record"
            )
        repair_entities = closure.get("repair_entities", [])
        if not isinstance(repair_entities, list) or not all(
            isinstance(item, str) and item for item in repair_entities
        ):
            raise IntegrityError("closure repair_entities must be a list of IDs")
        for entity_id in affected:
            entity = self.find_entity(entity_id)
            if entity["payload"].get("status") == "VALID":
                continue
            if entity_id in repair_entities:
                raise IntegrityError(
                    f"affected entity {entity_id} is listed as both broken and repaired"
                )
            if not any(
                self.find_entity(repair_id)["payload"].get("status") == "VALID"
                for repair_id in repair_entities
            ):
                raise IntegrityError(
                    f"affected entity {entity_id} has no current VALID repair entity"
                )

        rerun_scope = set(original.get("rerun_scope", []))
        rerun_gates = closure.get("rerun_gates", [])
        if not isinstance(rerun_gates, list) or not rerun_gates:
            raise IntegrityError("finding closure requires re-run gate evidence")
        covered_stages: set[str] = set()
        for gate in rerun_gates:
            if not isinstance(gate, dict):
                raise IntegrityError("rerun gate record must be an object")
            stage = gate.get("stage")
            report_sha256 = gate.get("report_sha256")
            gate_sequence = gate.get("gate_event_sequence")
            if (
                not isinstance(stage, str)
                or not isinstance(report_sha256, str)
                or not SHA256_PATTERN.fullmatch(report_sha256)
                or isinstance(gate_sequence, bool)
                or not isinstance(gate_sequence, int)
                or gate_sequence <= finding_created_sequence
            ):
                raise IntegrityError("rerun gate record is malformed or predates the finding")
            events = [
                event
                for event in self._registry_events()
                if event.get("event_type") == "GATE_RECORDED"
                and int(event.get("sequence", -1)) == gate_sequence
                and event.get("stage") == stage
            ]
            if len(events) != 1:
                raise IntegrityError(
                    f"no unique GATE_RECORDED event at sequence {gate_sequence} for {stage}"
                )
            gate_payload = events[0].get("payload")
            if not isinstance(gate_payload, dict):
                raise IntegrityError("gate event payload is invalid")
            if (
                gate_payload.get("report_status") != "PASS"
                or gate_payload.get("report_sha256") != report_sha256
            ):
                raise IntegrityError(
                    f"rerun gate {stage}@seq{gate_sequence} is not a passing recorded gate"
                )
            covered_stages.add(stage)
        if not rerun_scope.issubset(covered_stages):
            raise IntegrityError(
                "rerun gates do not cover the finding's declared rerun scope: "
                + str(sorted(rerun_scope - covered_stages))
            )

        payload = deepcopy(original)
        payload["finding_status"] = mode
        payload["closure_evidence"] = list(closure_evidence)
        payload["closure_reason"] = reason.strip()
        payload["closure_status"] = "EVIDENCE_VERIFIED"
        payload["finding_closure"] = deepcopy(closure)
        self.validate_payload("finding", payload)
        return self._write_version("finding", payload, stage=latest.get("created_stage"))

    def iter_latest(self, kind: str) -> list[dict[str, Any]]:
        kind = self.normalize_kind(kind)
        self._recover_journal()
        head_key = self.ledger.head()["head_sha256"]
        if self._latest_list_cache_head != head_key:
            self._latest_list_cache_head = head_key
            self._latest_list_cache.clear()
        cached = self._latest_list_cache.get(kind)
        if cached is None:
            identities = self._committed_identity_map()
            cached = [
                self.latest(kind, entity_id)
                for entity_id, entity_kind in sorted(identities.items())
                if entity_kind == kind
            ]
            self._latest_list_cache[kind] = cached
        return [deepcopy(record) for record in cached]

    def validate_integrity(self, deep: bool = True) -> bool:
        self._recover_journal()
        committed: set[str] = set()
        for event in self._registry_events():
            if event["event_type"] == "REGISTRY_RECORDED":
                path = event["payload"].get("record_path")
                if not isinstance(path, str) or path in committed:
                    raise IntegrityError("duplicate or invalid registry event path")
                committed.add(path)
        observed = (
            {
                path.relative_to(self.project_root).as_posix()
                for path in self.root.rglob("*.json")
                if path.is_file()
            }
            if self.root.exists()
            else set()
        )
        if observed != committed:
            raise IntegrityError(
                "registry file set mismatch; "
                f"missing={sorted(committed - observed)}; orphan={sorted(observed - committed)}"
            )
        identities = self._committed_identity_map()
        if not deep:
            # Hot-path mode (register / status revision / finding closure):
            # file-set consistency, identity uniqueness and execution event
            # pairing are checked; per-record payload re-validation is skipped
            # because every record is hash-verified against its filename and
            # ledger entry whenever it is actually read.
            return True
        latest_records: dict[str, dict[str, Any]] = {}
        execution_versions: dict[str, list[dict[str, Any]]] = {}
        for entity_id, kind in identities.items():
            versions = self._committed_versions(kind, entity_id)
            latest_records[entity_id] = versions[-1]
            if kind == "execution":
                execution_versions[entity_id] = versions

        starts, finishes = self._execution_events()
        execution_ids = {
            entity_id for entity_id, kind in identities.items() if kind == "execution"
        }
        event_execution_ids = set(starts) | set(finishes)
        if event_execution_ids != execution_ids:
            raise IntegrityError(
                "execution event/Registry identity mismatch; "
                f"events_without_record={sorted(event_execution_ids - execution_ids)}; "
                f"records_without_events={sorted(execution_ids - event_execution_ids)}"
            )
        for execution_id in sorted(execution_ids):
            record = latest_records[execution_id]
            self._validate_execution(record["payload"], resolve_dependencies=False)
            self._validate_execution_attestation(
                record, execution_versions[execution_id], starts, finishes
            )
        return True
