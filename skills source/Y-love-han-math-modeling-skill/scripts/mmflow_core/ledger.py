from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .canonical import atomic_write_json, canonical_json_bytes, sha256_bytes
from .errors import IntegrityError


ZERO_HASH = "0" * 64
_EVENT_NAME_RE = re.compile(r"^(\d{6})_([0-9a-f]{64})\.json$")


class Ledger:
    def __init__(
        self,
        project_root: Path | str,
        policy_sha256: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.mmflow = self.project_root / ".mmflow"
        self.events_dir = self.mmflow / "events"
        self.head_path = self.mmflow / "ledger-head.json"
        self.transaction_path = self.mmflow / "ledger-transaction.json"
        self.policy_sha256 = policy_sha256
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def hash_head(head: dict[str, Any]) -> str:
        body = {key: value for key, value in head.items() if key != "head_sha256"}
        return sha256_bytes(canonical_json_bytes(body))

    @staticmethod
    def hash_event(event: dict[str, Any]) -> str:
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        return sha256_bytes(canonical_json_bytes(body))

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise IntegrityError(f"cannot read valid JSON: {path}") from error
        if not isinstance(value, dict):
            raise IntegrityError(f"expected JSON object: {path}")
        return value

    def _read_head(self) -> dict[str, Any]:
        if not self.head_path.is_file():
            raise IntegrityError("ledger head is missing")
        head = self._read_json(self.head_path)
        if head.get("head_sha256") != self.hash_head(head):
            raise IntegrityError("ledger head self-hash mismatch")
        if head.get("policy_sha256") != self.policy_sha256:
            raise IntegrityError("ledger policy hash mismatch")
        return head

    def _event_path(self, sequence: int, event_sha256: str) -> Path:
        return self.events_dir / f"{sequence:06d}_{event_sha256}.json"

    def _make_head(
        self, run_id: str, sequence: int, event_sha256: str, generation: int
    ) -> dict[str, Any]:
        head = {
            "head_version": 1,
            "run_id": run_id,
            "sequence": sequence,
            "event_sha256": event_sha256,
            "policy_sha256": self.policy_sha256,
            "generation": generation,
        }
        head["head_sha256"] = self.hash_head(head)
        return head

    def initialize(self, run_id: str) -> dict[str, Any]:
        if self.head_path.exists() or self.events_dir.exists():
            raise IntegrityError("ledger already initialized")
        self.events_dir.mkdir(parents=True)
        atomic_write_json(self.head_path, self._make_head(run_id, 0, ZERO_HASH, 0))
        return self.append(run_id, "RUN_INITIALIZED", {"run_id": run_id})

    def append(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        stage: str | None = None,
    ) -> dict[str, Any]:
        self.recover()
        head = self._read_head()
        if head["run_id"] != run_id:
            raise IntegrityError("run_id does not match ledger")
        sequence = int(head["sequence"]) + 1
        occurred = self.clock()
        if occurred.tzinfo is None:
            raise IntegrityError("ledger clock must return timezone-aware datetime")
        event = {
            "event_version": 1,
            "sequence": sequence,
            "run_id": run_id,
            "event_type": event_type,
            "stage": stage,
            "occurred_at": occurred.astimezone(timezone.utc).isoformat(),
            "local_timezone": str(occurred.astimezone().tzinfo),
            "payload": payload,
            "previous_event_sha256": head["event_sha256"],
            "policy_sha256": self.policy_sha256,
        }
        event["event_sha256"] = self.hash_event(event)
        event_path = self._event_path(sequence, event["event_sha256"])
        transaction = {
            "transaction_version": 1,
            "previous_head": head,
            "candidate_sequence": sequence,
            "candidate_event_sha256": event["event_sha256"],
            "candidate_filename": event_path.name,
        }
        atomic_write_json(self.transaction_path, transaction)
        atomic_write_json(event_path, event)
        verified = self._read_json(event_path)
        if verified.get("event_sha256") != self.hash_event(verified):
            raise IntegrityError("candidate event hash mismatch")
        new_head = self._make_head(
            run_id,
            sequence,
            event["event_sha256"],
            int(head["generation"]) + 1,
        )
        atomic_write_json(self.head_path, new_head)
        self.transaction_path.unlink()
        self._fast_validate(new_head)
        return event

    def recover(self) -> bool:
        if not self.transaction_path.exists():
            if self.head_path.exists():
                self._fast_validate(self._read_head())
            return False
        transaction = self._read_json(self.transaction_path)
        current_head = self._read_head()
        previous_head = transaction.get("previous_head")
        if not isinstance(previous_head, dict):
            raise IntegrityError("transaction has no valid previous head")
        if previous_head.get("head_sha256") != self.hash_head(previous_head):
            raise IntegrityError("transaction previous head is invalid")
        if previous_head.get("run_id") != current_head.get("run_id"):
            raise IntegrityError("transaction run_id differs from ledger")
        if previous_head.get("policy_sha256") != self.policy_sha256:
            raise IntegrityError("transaction previous head has wrong policy")
        candidate_path = self.events_dir / str(transaction.get("candidate_filename"))
        if not candidate_path.is_file():
            raise IntegrityError("transaction candidate event is missing")
        candidate = self._read_json(candidate_path)
        try:
            expected_sequence = int(transaction["candidate_sequence"])
            expected_hash = str(transaction["candidate_event_sha256"])
        except (KeyError, TypeError, ValueError) as error:
            raise IntegrityError("transaction candidate identity is invalid") from error
        if expected_sequence != int(previous_head["sequence"]) + 1:
            raise IntegrityError("transaction candidate is not the next sequence")
        if candidate_path.name != f"{expected_sequence:06d}_{expected_hash}.json":
            raise IntegrityError("transaction candidate filename mismatch")
        if candidate.get("sequence") != expected_sequence:
            raise IntegrityError("transaction sequence mismatch")
        if candidate.get("event_sha256") != expected_hash:
            raise IntegrityError("transaction event hash mismatch")
        if self.hash_event(candidate) != expected_hash:
            raise IntegrityError("transaction candidate content mismatch")
        if candidate.get("previous_event_sha256") != previous_head.get("event_sha256"):
            raise IntegrityError("transaction candidate previous link mismatch")
        if candidate.get("run_id") != previous_head.get("run_id"):
            raise IntegrityError("transaction candidate run_id mismatch")
        if candidate.get("policy_sha256") != self.policy_sha256:
            raise IntegrityError("transaction candidate policy mismatch")
        if current_head["sequence"] == expected_sequence:
            if (
                current_head["event_sha256"] != expected_hash
                or current_head.get("generation")
                != int(previous_head["generation"]) + 1
            ):
                raise IntegrityError("committed head differs from transaction")
        elif current_head.get("head_sha256") == previous_head.get("head_sha256"):
            committed = self._make_head(
                current_head["run_id"],
                expected_sequence,
                expected_hash,
                int(current_head["generation"]) + 1,
            )
            atomic_write_json(self.head_path, committed)
        else:
            raise IntegrityError("transaction and ledger head conflict")
        self.transaction_path.unlink()
        self.validate()
        return True

    def _fast_validate(self, head: dict[str, Any]) -> bool:
        """Structural chain check without parsing event bodies.

        Event filenames embed each event's content hash, so filename order and
        format verify the committed sequence cheaply; the tail body is opened
        once to confirm it matches the head.  Deep per-event content
        verification remains in :meth:`validate`, which gate/audit paths run
        explicitly.  This keeps steady-state command cost near O(1) file reads
        while still detecting deletion, reordering, truncation, count drift
        and tail corruption.
        """
        files = sorted(self.events_dir.glob("*.json"))
        if len(files) != int(head["sequence"]):
            raise IntegrityError("event count differs from committed head")
        if not files:
            if head["event_sha256"] != ZERO_HASH:
                raise IntegrityError("tail event does not match committed head")
            return True
        previous_name_hash = ZERO_HASH
        for expected_sequence, path in enumerate(files, start=1):
            match = _EVENT_NAME_RE.match(path.name)
            if match is None:
                raise IntegrityError("event filename has no numeric sequence")
            if int(match.group(1)) != expected_sequence:
                raise IntegrityError("event sequence mismatch")
            if expected_sequence == len(files):
                tail_previous_from_names = previous_name_hash
            previous_name_hash = match.group(2)
        tail = self._read_json(files[-1])
        digest = self.hash_event(tail)
        if (
            tail.get("sequence") != int(head["sequence"])
            or digest != head["event_sha256"]
            or files[-1].name != f"{int(head['sequence']):06d}_{digest}.json"
            or tail.get("previous_event_sha256") != tail_previous_from_names
        ):
            raise IntegrityError("tail event does not match committed head")
        return True

    def contains_event_hash(self, event_sha256: str) -> bool:
        """Return True when an event file with this content hash is on disk.

        Filenames embed each event's content hash, so membership needs no
        body parsing.  Used by the runtime trust cache to recognise heads it
        has already deep-verified.
        """
        if not self.events_dir.is_dir():
            return False
        for path in self.events_dir.glob("*.json"):
            match = _EVENT_NAME_RE.match(path.name)
            if match is not None and match.group(2) == event_sha256:
                return True
        return False

    def validate_fast(self) -> bool:
        """Recover any pending transaction, then run the structural fast check."""
        self.recover()
        self._fast_validate(self._read_head())
        return True

    def validate(self) -> bool:
        head = self._read_head()
        files = sorted(self.events_dir.glob("*.json"))
        sequences: list[int] = []
        for path in files:
            prefix = path.name.split("_", 1)[0]
            if not prefix.isdigit():
                raise IntegrityError("event filename has no numeric sequence")
            sequences.append(int(prefix))
        if len(sequences) != len(set(sequences)):
            raise IntegrityError("ledger contains duplicate event sequence")
        if len(files) != int(head["sequence"]):
            raise IntegrityError("event count differs from committed head")
        previous = ZERO_HASH
        for expected_sequence, path in enumerate(files, start=1):
            event = self._read_json(path)
            digest = self.hash_event(event)
            expected_name = f"{expected_sequence:06d}_{digest}.json"
            if path.name != expected_name:
                raise IntegrityError("event filename or sequence mismatch")
            if event.get("sequence") != expected_sequence:
                raise IntegrityError("event sequence mismatch")
            if event.get("event_sha256") != digest:
                raise IntegrityError("event content hash mismatch")
            if event.get("previous_event_sha256") != previous:
                raise IntegrityError("event link mismatch")
            if event.get("run_id") != head["run_id"]:
                raise IntegrityError("event run_id mismatch")
            if event.get("policy_sha256") != self.policy_sha256:
                raise IntegrityError("event policy hash mismatch")
            previous = digest
        if previous != head["event_sha256"]:
            raise IntegrityError("tail event does not match committed head")
        return True

    def read_events(self) -> list[dict[str, Any]]:
        self.recover()
        self.validate_fast()
        return [self._read_json(path) for path in sorted(self.events_dir.glob("*.json"))]

    def head(self) -> dict[str, Any]:
        self.recover()
        self.validate_fast()
        return dict(self._read_head())
