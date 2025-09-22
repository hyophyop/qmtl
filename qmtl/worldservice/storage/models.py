"""Dataclasses describing the in-memory storage records."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, MutableMapping, Optional


@dataclass
class WorldRecord:
    """Persisted world metadata."""

    id: str
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "WorldRecord":
        try:
            raw_id = payload["id"]
        except KeyError as exc:  # pragma: no cover - defensive: API validates id
            raise KeyError("world payload missing 'id'") from exc
        if not isinstance(raw_id, str) or not raw_id:
            raise ValueError("world id must be a non-empty string")
        data = dict(payload)
        data["id"] = raw_id
        return cls(id=raw_id, data=data)

    def update(self, updates: Mapping[str, Any]) -> None:
        if "id" in updates and updates["id"] != self.id:
            raise ValueError("world id is immutable")
        self.data.update(dict(updates))

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.data)


@dataclass
class PolicyVersion:
    """A single policy revision."""

    version: int
    payload: Any


@dataclass
class WorldPolicies:
    """Policy versions for a world."""

    versions: Dict[int, PolicyVersion] = field(default_factory=dict)
    default: Optional[int] = None

    def clone(self) -> "WorldPolicies":
        return WorldPolicies(
            versions={version: PolicyVersion(version=version, payload=value.payload) for version, value in self.versions.items()},
            default=self.default,
        )


@dataclass
class ActivationEntry:
    """Single activation state snapshot for a strategy side."""

    active: bool
    weight: float
    freeze: bool
    drain: bool
    effective_mode: Optional[str]
    run_id: Optional[str]
    ts: str
    etag: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active": self.active,
            "weight": self.weight,
            "freeze": self.freeze,
            "drain": self.drain,
            "effective_mode": self.effective_mode,
            "run_id": self.run_id,
            "ts": self.ts,
            "etag": self.etag,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ActivationEntry":
        return cls(
            active=bool(payload.get("active", False)),
            weight=float(payload.get("weight", 1.0)),
            freeze=bool(payload.get("freeze", False)),
            drain=bool(payload.get("drain", False)),
            effective_mode=payload.get("effective_mode"),
            run_id=payload.get("run_id"),
            ts=str(payload["ts"]),
            etag=str(payload["etag"]),
        )


@dataclass
class ActivationState:
    """Internal activation representation leveraging dataclasses."""

    version: int = 0
    state: Dict[str, Dict[str, ActivationEntry]] = field(default_factory=dict)

    def clone(self) -> "ActivationState":
        return ActivationState(
            version=self.version,
            state={
                strategy_id: {side: ActivationEntry.from_payload(entry.to_dict()) for side, entry in sides.items()}
                for strategy_id, sides in self.state.items()
            },
        )


@dataclass
class WorldActivation:
    """Activation snapshot returned by the façade to callers."""

    version: int = 0
    state: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)

    @classmethod
    def from_internal(cls, internal: ActivationState) -> "WorldActivation":
        return cls(
            version=internal.version,
            state={
                strategy_id: {side: entry.to_dict() for side, entry in sides.items()}
                for strategy_id, sides in internal.state.items()
            },
        )

    def to_internal(self) -> ActivationState:
        return ActivationState(
            version=self.version,
            state={
                strategy_id: {
                    side: ActivationEntry.from_payload(entry)
                    for side, entry in sides.items()
                }
                for strategy_id, sides in self.state.items()
            },
        )


@dataclass
class WorldAuditLog:
    """Audit entries for a world."""

    entries: list[Dict[str, Any]] = field(default_factory=list)

    def clone(self) -> "WorldAuditLog":
        return WorldAuditLog(entries=[dict(entry) for entry in self.entries])


@dataclass
class ValidationCacheEntry:
    """Cached validation result scoped by ExecutionDomain."""

    eval_key: str
    node_id: str
    execution_domain: str
    contract_id: str
    dataset_fingerprint: str
    code_version: str
    resource_policy: str
    result: str
    metrics: Dict[str, Any]
    timestamp: str

    def clone(self) -> "ValidationCacheEntry":
        return ValidationCacheEntry(
            eval_key=self.eval_key,
            node_id=self.node_id,
            execution_domain=self.execution_domain,
            contract_id=self.contract_id,
            dataset_fingerprint=self.dataset_fingerprint,
            code_version=self.code_version,
            resource_policy=self.resource_policy,
            result=self.result,
            metrics=dict(self.metrics),
            timestamp=self.timestamp,
        )


@dataclass
class WorldNodeRef:
    """Metadata describing a world/node mapping."""

    world_id: str
    node_id: str
    execution_domain: str
    status: str
    last_eval_key: Optional[str] = None
    annotations: Any | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_id": self.world_id,
            "node_id": self.node_id,
            "execution_domain": self.execution_domain,
            "status": self.status,
            "last_eval_key": self.last_eval_key,
            "annotations": deepcopy(self.annotations) if self.annotations is not None else None,
        }

    def clone(self) -> "WorldNodeRef":
        return WorldNodeRef(**self.to_dict())


@dataclass
class EdgeOverrideRecord:
    """Override state for a graph edge."""

    src_node_id: str
    dst_node_id: str
    active: bool
    updated_at: str
    reason: Optional[str] = None

    def to_dict(self, world_id: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "world_id": world_id,
            "src_node_id": self.src_node_id,
            "dst_node_id": self.dst_node_id,
            "active": self.active,
            "updated_at": self.updated_at,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload

    def clone(self) -> "EdgeOverrideRecord":
        return EdgeOverrideRecord(
            src_node_id=self.src_node_id,
            dst_node_id=self.dst_node_id,
            active=self.active,
            updated_at=self.updated_at,
            reason=self.reason,
        )


__all__ = [
    "ActivationEntry",
    "ActivationState",
    "EdgeOverrideRecord",
    "PolicyVersion",
    "ValidationCacheEntry",
    "WorldActivation",
    "WorldAuditLog",
    "WorldNodeRef",
    "WorldPolicies",
    "WorldRecord",
]
