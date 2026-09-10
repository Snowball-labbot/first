from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .canonical import atomic_write_json, canonical_json_bytes, sha256_bytes
from .errors import GateFailedError, IntegrityError
from .gates import verify_gate_report
from .ledger import Ledger


STAGES = tuple(f"P{index}" for index in range(12))


class Workflow:
    def __init__(
        self,
        project_root: Path | str,
        ledger: Ledger,
        run_id: str,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.ledger = ledger
        self.run_id = run_id
        self.state_path = self.project_root / ".mmflow" / "state.json"

    def _empty_state(self) -> dict[str, Any]:
        return {
            "state_version": 2,
            "run_id": self.run_id,
            "stages": {stage: "NOT_STARTED" for stage in STAGES},
            "active_stage": None,
            "last_gate": {},
            "complete": False,
            "ledger_head_sha256": None,
            "stage_epochs": {stage: 0 for stage in STAGES},
            "blocked": None,
        }

    def _replay(self) -> dict[str, Any]:
        state = self._empty_state()
        for event in self.ledger.read_events():
            if event["run_id"] != self.run_id:
                raise IntegrityError("workflow event belongs to another run")
            event_type = event["event_type"]
            stage = event.get("stage")
            payload = event["payload"]
            if event_type == "STAGE_BEGUN":
                if state["active_stage"] is not None:
                    raise IntegrityError("event history contains two active stages")
                state["stages"][stage] = "ACTIVE"
                state["active_stage"] = stage
                state["stage_epochs"][stage] = int(state["stage_epochs"][stage]) + 1
            elif event_type == "WORKFLOW_BLOCKED":
                if state["active_stage"] != stage:
                    raise IntegrityError("blocked stage was not active")
                state["stages"][stage] = "BLOCKED"
                state["active_stage"] = None
                state["blocked"] = {
                    "stage": stage,
                    "event_sequence": int(event["sequence"]),
                    "payload": deepcopy(payload),
                }
            elif event_type == "INTEGRITY_FAILURE_RECORDED":
                if stage in STAGES:
                    state["stages"][stage] = "INTEGRITY_FAILURE"
                state["active_stage"] = None
            elif event_type == "GATE_RECORDED":
                if state["active_stage"] != stage:
                    raise IntegrityError("gate was recorded for a non-active stage")
                state["last_gate"][stage] = payload
                if payload["report_status"] == "PASS":
                    state["stages"][stage] = "ACTIVE"
                elif payload["report_status"] == "BLOCKED":
                    state["stages"][stage] = "BLOCKED"
                    state["active_stage"] = None
                else:
                    state["stages"][stage] = "GATE_FAILED"
            elif event_type == "STAGE_ADVANCED":
                if state["active_stage"] != stage:
                    raise IntegrityError("advanced stage was not active")
                state["stages"][stage] = "PASSED"
                state["active_stage"] = None
                if stage == "P11":
                    state["complete"] = True
            elif event_type == "WORKFLOW_ROLLED_BACK":
                target = payload["target_stage"]
                target_index = STAGES.index(target)
                for index, candidate in enumerate(STAGES):
                    if index < target_index:
                        continue
                    state["stages"][candidate] = (
                        "ACTIVE" if candidate == target else "INVALIDATED"
                    )
                    state["last_gate"].pop(candidate, None)
                state["active_stage"] = target
                state["complete"] = False
                # 回退是 BLOCKED 阶段的合法逃生路径：目标阶段重新激活意味着
                # 旧阻塞已被放弃，残留的 blocked 记录会误导 next/resume。
                state["blocked"] = None
                state["stage_epochs"][target] = int(state["stage_epochs"][target]) + 1
            elif event_type == "WORKFLOW_RESUMED":
                if state["active_stage"] is not None:
                    raise IntegrityError("cannot resume while a stage is active")
                if state["stages"].get(stage) != "BLOCKED":
                    raise IntegrityError("resumed stage was not blocked")
                state["stages"][stage] = "ACTIVE"
                state["active_stage"] = stage
                # The block was an external interruption, not a discarded
                # generation: the stage keeps its epoch (its evidence is still
                # the same work), but the old gate result must not carry over.
                state["last_gate"].pop(stage, None)
                state["blocked"] = None
        state["ledger_head_sha256"] = self.ledger.head()["head_sha256"]
        return state

    def _read_view(self) -> dict[str, Any] | None:
        if not self.state_path.is_file():
            return None
        try:
            value = json.loads(self.state_path.read_text("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _record_view_mismatch(self, observed, expected_state: dict[str, Any]) -> None:
        """把派生视图失配记入旁路日志（不触碰 state.json 与账本）。

        只读路径不得写账本（未持锁会与并发写进程的事务交错），也不得向
        state.json 注入额外键（下一次无失配重放会把键移除，令 integrity
        缓存记录的哈希再次失配、信任前沿无法恢复）。旁路文件仅供审计
        发现，不参与任何哈希契约。
        """
        try:
            entry = {
                "run_id": self.run_id,
                "expected_state_sha256": sha256_bytes(canonical_json_bytes(expected_state)),
                "observed_state_sha256": (
                    sha256_bytes(canonical_json_bytes(observed))
                    if observed is not None
                    else None
                ),
            }
            path = self.state_path.parent / "derived-view-mismatch.json"
            history: list = []
            if path.is_file():
                try:
                    loaded = json.loads(path.read_text("utf-8"))
                    if isinstance(loaded, list):
                        history = loaded
                except (OSError, UnicodeError, json.JSONDecodeError):
                    history = []
            history.append(entry)
            atomic_write_json(path, history[-50:])
        except (OSError, TypeError, ValueError):
            # 审计旁路失败不影响修复本身；state 视图已重建。
            pass

    def _persist_and_return(self, expected_previous_head: str | None = None) -> dict[str, Any]:
        state = self._replay()
        observed = self._read_view()
        semantic_keys = (
            "state_version",
            "run_id",
            "stages",
            "active_stage",
            "last_gate",
            "complete",
        )
        semantic_mismatch = observed is not None and any(
            observed.get(key) != state[key] for key in semantic_keys
        )
        if semantic_mismatch and expected_previous_head is None:
            # 只读路径：就地重建派生视图，失配事实记入旁路审计文件；
            # 写路径（expected_previous_head 非空）行为不变——其失配由
            # 调用方命令的完整性与门禁流程处理。
            self._record_view_mismatch(observed, state)
        atomic_write_json(self.state_path, state)
        return deepcopy(state)

    def state(self) -> dict[str, Any]:
        # Fast path: the persisted view already carries the ledger head it was
        # derived from, and the loader only marks the view trusted after its
        # content hash matched the verified frontier.  Replaying every event
        # adds no information in that case; reuse the view to keep
        # steady-state command cost flat.
        if getattr(self, "_trusted_view_ok", False):
            view = self._read_view()
            if (
                isinstance(view, dict)
                and view.get("ledger_head_sha256")
                and view.get("ledger_head_sha256") == self.ledger.head()["head_sha256"]
            ):
                return deepcopy(view)
        return self._persist_and_return()

    def snapshot(self) -> dict[str, Any]:
        """Read-only replay without persisting the derived view.

        Used by the Registry epoch resolver: the epoch value only changes on
        begin/rollback/resume events, so a registration never needs to pay
        for the atomic state write of a full ``state()`` call.
        """
        return self._replay()

    @staticmethod
    def _next_legal_stage(state: dict[str, Any]) -> str | None:
        for stage in STAGES:
            status = state["stages"][stage]
            if status in {"NOT_STARTED", "INVALIDATED"}:
                return stage
            if status != "PASSED":
                return None
        return None

    def _append_and_persist(
        self, event_type: str, payload: dict[str, Any], stage: str | None
    ) -> dict[str, Any]:
        previous_head = self.ledger.head()["head_sha256"]
        event = self.ledger.append(self.run_id, event_type, payload, stage=stage)
        self._persist_and_return(expected_previous_head=previous_head)
        return event

    def begin(self, stage: str) -> dict[str, Any]:
        if stage not in STAGES:
            raise IntegrityError(f"unknown stage: {stage}")
        state = self._replay()
        if state["complete"]:
            raise IntegrityError("workflow is already complete")
        if state["active_stage"] is not None:
            raise IntegrityError("another stage is already active")
        if any(status == "BLOCKED" for status in state["stages"].values()):
            raise IntegrityError("blocked workflow must be resumed explicitly")
        if self._next_legal_stage(state) != stage:
            raise IntegrityError(f"stage cannot begin yet: {stage}")
        return self._append_and_persist("STAGE_BEGUN", {}, stage)

    def record_gate(
        self,
        stage: str,
        report: dict[str, Any],
        evidence_fingerprint: str,
    ) -> dict[str, Any]:
        state = self._replay()
        if state["active_stage"] != stage:
            raise IntegrityError("gate stage is not active")
        report_status = report.get("status")
        if report_status not in {"PASS", "FAIL", "ERROR"}:
            raise IntegrityError(
                "invalid aggregate gate status; BLOCKED uses the atomic "
                "workflow.block transition, not record_gate"
            )
        required_report_fields = (
            "gate_id",
            "policy_version",
            "evidence_fingerprint",
            "checks",
            "json_report_path",
            "markdown_report_path",
            "markdown_sha256",
            "report_sha256",
        )
        if any(field not in report for field in required_report_fields):
            raise IntegrityError("gate report must be persisted and fully hashed before recording")
        payload = {
            "report_status": report_status,
            "report_sha256": report.get("report_sha256")
            or sha256_bytes(canonical_json_bytes(report)),
            "evidence_fingerprint": evidence_fingerprint,
        }
        report_paths = (
            report.get("json_report_path"),
            report.get("markdown_report_path"),
            report.get("markdown_sha256"),
        )
        if not all(isinstance(value, str) and value for value in report_paths):
            raise IntegrityError("persisted gate report metadata is incomplete")
        try:
            verify_gate_report(report, self.project_root)
        except (OSError, ValueError) as error:
            raise IntegrityError("persisted gate report failed verification") from error
        payload.update(
            {
                "gate_id": report.get("gate_id"),
                "json_report_path": report_paths[0],
                "markdown_report_path": report_paths[1],
                "markdown_sha256": report_paths[2],
            }
        )
        return self._append_and_persist("GATE_RECORDED", payload, stage)

    def _verify_persisted_gate(
        self, stage: str, gate: dict[str, Any], evidence_fingerprint: str
    ) -> None:
        path = gate.get("json_report_path")
        if path is None:
            return
        try:
            report_path = self.project_root / str(path)
            report = json.loads(report_path.read_text("utf-8"))
            if not isinstance(report, dict):
                raise ValueError("gate report is not an object")
            verify_gate_report(report, self.project_root)
            if (
                report.get("gate_id") != stage
                or report.get("status") != "PASS"
                or report.get("report_sha256") != gate.get("report_sha256")
                or report.get("evidence_fingerprint") != evidence_fingerprint
                or report.get("markdown_report_path")
                != gate.get("markdown_report_path")
                or report.get("markdown_sha256") != gate.get("markdown_sha256")
            ):
                raise ValueError("gate event and persisted report differ")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise GateFailedError(
                "persisted passing gate report failed integrity verification"
            ) from error

    def advance(self, evidence_fingerprint: str) -> dict[str, Any]:
        state = self._replay()
        stage = state["active_stage"]
        if stage is None:
            raise GateFailedError("no active stage")
        gate = state["last_gate"].get(stage)
        if not gate or gate["report_status"] != "PASS":
            raise GateFailedError("active stage has no passing gate")
        if gate["evidence_fingerprint"] != evidence_fingerprint:
            raise GateFailedError("gate evidence is stale")
        self._verify_persisted_gate(stage, gate, evidence_fingerprint)
        return self._append_and_persist("STAGE_ADVANCED", {}, stage)

    def rollback(self, stage: str, reason: str) -> dict[str, Any]:
        if stage not in STAGES or not reason.strip():
            raise IntegrityError("rollback requires a valid stage and non-empty reason")
        state = self._replay()
        reached = [
            candidate
            for candidate in STAGES
            if state["stages"][candidate] != "NOT_STARTED"
        ]
        if stage not in reached:
            raise IntegrityError("cannot roll back to an unreached stage")
        return self._append_and_persist(
            "WORKFLOW_ROLLED_BACK",
            {"target_stage": stage, "reason": reason.strip()},
            stage,
        )

    BLOCK_PAYLOAD_FIELDS = (
        "missing_item",
        "why_required",
        "attempted_alternatives",
        "minimum_request",
        "safe_partial_outputs",
        "resume_command",
    )

    def block(self, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Atomically enter the BLOCKED lifecycle with a structured payload.

        BLOCKED is a single state event, not ``record_gate(BLOCKED)`` followed
        by a separate transition.  The payload must carry the full resolution
        contract; a bare reason is rejected so an AI cannot block without
        saying what is missing, why, what was tried, what still works, and the
        exact command that resumes the workflow.
        """
        if stage not in STAGES:
            raise IntegrityError(f"unknown stage: {stage}")
        if not isinstance(payload, dict) or not payload:
            raise IntegrityError("block requires a structured payload")
        missing = [
            field for field in self.BLOCK_PAYLOAD_FIELDS if field not in payload
        ]
        if missing:
            raise IntegrityError(
                "block payload must include: " + ", ".join(missing)
            )
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise IntegrityError("block payload requires a non-empty reason")
        if not isinstance(payload["minimum_request"], dict) or not payload[
            "minimum_request"
        ]:
            raise IntegrityError("block payload minimum_request must be a non-empty object")
        for field in ("attempted_alternatives", "safe_partial_outputs"):
            if not isinstance(payload[field], list) or not all(
                isinstance(item, str) and item for item in payload[field]
            ):
                raise IntegrityError(f"block payload {field} must be a list of strings")
        if not isinstance(payload["missing_item"], str) or not payload[
            "missing_item"
        ].strip():
            raise IntegrityError("block payload missing_item must be a non-empty string")
        if not isinstance(payload["why_required"], str) or not payload[
            "why_required"
        ].strip():
            raise IntegrityError("block payload why_required must be a non-empty string")
        if not isinstance(payload["resume_command"], str) or not payload[
            "resume_command"
        ].strip():
            raise IntegrityError("block payload resume_command must be a non-empty string")
        state = self._replay()
        if state["active_stage"] != stage:
            raise IntegrityError("block requires the stage to be active")
        committed = deepcopy(payload)
        committed["reason"] = reason.strip()
        return self._append_and_persist("WORKFLOW_BLOCKED", committed, stage)

    def resume_blocked(
        self,
        resolution_evidence_ids: list[str] | None = None,
        evidence_validator: Any = None,
    ) -> dict[str, Any]:
        """Resume a blocked workflow only with evidence created after the block.

        ``evidence_validator`` is an optional callable ``(evidence_id) -> None``
        that raises unless the evidence is current VALID evidence created after
        the WORKFLOW_BLOCKED event sequence.  Without resolution evidence the
        workflow stays blocked: nothing may resume on the same old evidence.
        Resumption clears the previous gate result so the stage must be gated
        again; the stage keeps its epoch because the blocked work was not a
        discarded generation.
        """
        state = self._replay()
        blocked = [
            stage for stage, status in state["stages"].items() if status == "BLOCKED"
        ]
        if len(blocked) != 1 or state["active_stage"] is not None:
            raise IntegrityError("workflow has no unique blocked stage")
        block_event_sequence = int(state["blocked"]["event_sequence"])
        if not isinstance(resolution_evidence_ids, list) or not resolution_evidence_ids:
            raise IntegrityError(
                "resuming a blocked workflow requires resolution evidence "
                "created after the block event"
            )
        if len(resolution_evidence_ids) != len(set(resolution_evidence_ids)):
            raise IntegrityError("resolution evidence IDs must be unique")
        if evidence_validator is None:
            raise IntegrityError(
                "resume requires an evidence validator bound to the Registry"
            )
        for evidence_id in resolution_evidence_ids:
            evidence_validator(evidence_id, block_event_sequence)
        return self._append_and_persist(
            "WORKFLOW_RESUMED",
            {
                "resolution_evidence_ids": list(resolution_evidence_ids),
                "block_event_sequence": block_event_sequence,
            },
            blocked[0],
        )
