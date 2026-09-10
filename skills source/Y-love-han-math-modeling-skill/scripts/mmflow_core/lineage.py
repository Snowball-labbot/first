from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from .errors import IntegrityError
from .registry import Registry


KINDS = (
    "execution",
    "artifact",
    "result",
    "claim",
    "formula",
    "figure",
    "citation",
    "finding",
    "evidence",
    "split",
)

STAGE_INDEX = {f"P{index}": index for index in range(12)}


def stage_index(stage: str) -> int:
    if stage not in STAGE_INDEX:
        raise IntegrityError(f"unknown stage: {stage}")
    return STAGE_INDEX[stage]


def entity_dependencies(kind: str, payload: dict) -> set[str]:
    if kind == "execution":
        return set(payload.get("source_artifact_ids", [])) | set(
            payload.get("dataset_split_ids", [])
        )
    if kind == "split":
        return {payload.get("source_dataset_artifact_id")} - {None}
    if kind == "artifact":
        dependencies = set(payload.get("inputs", []))
        if payload.get("artifact_class") == "production" and payload.get("execution_id"):
            dependencies.add(payload["execution_id"])
        return dependencies
    if kind == "result":
        return {payload["artifact_id"], payload["execution_id"]}
    if kind == "claim":
        return set(payload.get("supports", [])) | set(payload.get("counterevidence", []))
    if kind == "formula":
        return set(payload.get("dependencies", [])) | set(payload.get("citations", []))
    if kind == "figure":
        return {
            payload["artifact_id"],
            payload["sidecar_artifact_id"],
            *payload.get("source_results", []),
            *payload.get("caption_claims", []),
        }
    if kind == "finding":
        return (
            set(payload.get("evidence", []))
            | set(payload.get("affected_claims", []))
            | set(payload.get("closure_evidence", []))
        )
    if kind == "evidence":
        return set(payload.get("supports", []))
    return set()


class LineageGraph:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.kind_by_id: dict[str, str] = {}
        self.dependencies: dict[str, set[str]] = {}
        self.children: dict[str, set[str]] = defaultdict(set)
        for kind in KINDS:
            for record in registry.iter_latest(kind):
                entity_id = record["entity_id"]
                if entity_id in self.kind_by_id:
                    raise IntegrityError(f"entity ID is not globally unique: {entity_id}")
                self.kind_by_id[entity_id] = kind
                self.dependencies[entity_id] = entity_dependencies(kind, record["payload"])
        for entity_id, dependencies in self.dependencies.items():
            for dependency in dependencies:
                if dependency not in self.kind_by_id:
                    raise IntegrityError(f"unknown lineage dependency: {dependency}")
                self.children[dependency].add(entity_id)
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        indegree = {
            entity_id: len(dependencies)
            for entity_id, dependencies in self.dependencies.items()
        }
        queue = deque(sorted(entity_id for entity_id, degree in indegree.items() if degree == 0))
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for child in sorted(self.children.get(current, set())):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if visited != len(indegree):
            raise IntegrityError("lineage graph contains a cycle")

    def descendants(self, roots: Iterable[str]) -> list[str]:
        queue = deque(roots)
        visited: set[str] = set()
        while queue:
            current = queue.popleft()
            if current not in self.kind_by_id:
                raise KeyError(current)
            if current in visited:
                continue
            visited.add(current)
            queue.extend(sorted(self.children.get(current, set())))
        return sorted(visited)

    def invalidate_from(
        self,
        roots: Iterable[str],
        reason: str,
        root_status: str = "STALE",
    ) -> list[str]:
        root_ids = set(roots)
        affected = self.descendants(root_ids)
        for entity_id in affected:
            kind = self.kind_by_id[entity_id]
            latest = self.registry.latest(kind, entity_id)["payload"]
            target_status = root_status if entity_id in root_ids else "STALE"
            if latest["status"] != target_status:
                # F1: monotonic guard - never retroactively lower trust
                # below a status an entity already reached.
                from .registry import STATUS_RANK
                if STATUS_RANK.get(target_status, -1) <= STATUS_RANK.get(
                    latest["status"], -1
                ):
                    continue
                self.registry.revise_status(kind, entity_id, target_status, reason)
        return affected

    def earliest_affected_stage(self, affected: Iterable[str]) -> str | None:
        """Earliest P-stage that produced any affected entity."""
        candidates: list[str] = []
        for entity_id in affected:
            kind = self.kind_by_id[entity_id]
            record = self.registry.latest(kind, entity_id)
            payload = record["payload"]
            stage = payload.get("stage")
            if kind == "execution" and isinstance(stage, str) and stage in STAGE_INDEX:
                candidates.append(stage)
            created = record.get("created_stage")
            if isinstance(created, str) and created in STAGE_INDEX:
                candidates.append(created)
        if not candidates:
            return None
        return min(candidates, key=lambda stage: STAGE_INDEX[stage])


def rerun_scope_from(stage: str | None) -> list[str]:
    if stage is None:
        return []
    start = stage_index(stage)
    return [f"P{index}" for index in range(start, 12)]


def invalidate_stage_downstream(
    registry, target_stage: str, reason: str
) -> list[str]:
    """Mark STALE every entity created in a stage at or after *target_stage*.

    Called as part of a rollback so old-epoch evidence can never be reused
    after the workflow generation that produced it was discarded.  Immutable
    external input artifacts are preserved: they are the upstream sources a
    re-run depends on, not downstream claims.
    """
    target = stage_index(target_stage)
    affected: list[str] = []
    for kind in KINDS:
        for record in registry.iter_latest(kind):
            payload = record["payload"]
            if payload.get("status") in {"INVALID", "REVOKED"}:
                continue
            if kind == "artifact" and payload.get("artifact_class") == "external":
                continue
            created = record.get("created_stage")
            if created not in STAGE_INDEX:
                continue
            if STAGE_INDEX[created] < target:
                continue
            if payload.get("status") == "STALE":
                continue
            registry.revise_status(kind, record["entity_id"], "STALE", reason)
            affected.append(record["entity_id"])
    return sorted(affected)
