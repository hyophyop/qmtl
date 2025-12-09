"""Dataclasses describing the in-memory storage records."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional


def _iso_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass
class WorldRecord:
    """Persisted world metadata with audit-friendly defaults."""

    id: str
    name: str | None = None
    description: str | None = None
    owner: str | None = None
    labels: list[str] = field(default_factory=list)
    state: str = "ACTIVE"
    allow_live: bool = False
    circuit_breaker: bool = False
    default_policy_version: int | None = None
    created_at: str = field(default_factory=_iso_timestamp)
    updated_at: str = field(default_factory=_iso_timestamp)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "WorldRecord":
        try:
            raw_id = payload["id"]
        except KeyError as exc:  # pragma: no cover - defensive: API validates id
            raise KeyError("world payload missing 'id'") from exc
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise ValueError("world id must be a non-empty string")
        world_id = raw_id.strip()

        metadata = {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "id",
                "name",
                "description",
                "owner",
                "labels",
                "state",
                "allow_live",
                "circuit_breaker",
                "default_policy_version",
                "created_at",
                "updated_at",
            }
        }

        labels = cls._normalize_labels(payload.get("labels"))
        state = cls._normalize_state(payload.get("state", "ACTIVE"))
        created_at = str(payload.get("created_at") or _iso_timestamp())
        updated_at = str(payload.get("updated_at") or created_at)

        default_policy_version = payload.get("default_policy_version")
        if default_policy_version is not None:
            try:
                default_policy_version = int(default_policy_version)
            except (TypeError, ValueError) as exc:  # pragma: no cover - validation
                raise ValueError("default_policy_version must be an integer") from exc

        return cls(
            id=world_id,
            name=cls._normalize_optional_str(payload.get("name")),
            description=cls._normalize_optional_str(payload.get("description")),
            owner=cls._normalize_optional_str(payload.get("owner")),
            labels=labels,
            state=state,
            allow_live=bool(payload.get("allow_live", False)),
            circuit_breaker=bool(payload.get("circuit_breaker", False)),
            default_policy_version=default_policy_version,
            created_at=created_at,
            updated_at=updated_at,
            metadata=metadata,
        )

    def update(self, updates: Mapping[str, Any]) -> None:
        if "id" in updates and updates["id"] != self.id:
            raise ValueError("world id is immutable")

        name = self._normalize_optional_str(updates.get("name", self.name))
        description = self._normalize_optional_str(
            updates.get("description", self.description)
        )
        owner = self._normalize_optional_str(updates.get("owner", self.owner))
        state = self._normalize_state(updates.get("state", self.state))
        labels = self._normalize_labels(updates.get("labels", self.labels))
        default_policy_version = updates.get(
            "default_policy_version", self.default_policy_version
        )
        if default_policy_version is not None:
            try:
                default_policy_version = int(default_policy_version)
            except (TypeError, ValueError) as exc:  # pragma: no cover - validation
                raise ValueError("default_policy_version must be an integer") from exc

        self.name = name
        self.description = description
        self.owner = owner
        self.state = state
        self.labels = labels
        self.allow_live = bool(updates.get("allow_live", self.allow_live))
        self.circuit_breaker = bool(
            updates.get("circuit_breaker", self.circuit_breaker)
        )
        self.default_policy_version = default_policy_version
        self.metadata.update(
            {
                key: value
                for key, value in updates.items()
                if key
                not in {
                    "id",
                    "name",
                    "description",
                    "owner",
                    "labels",
                    "state",
                    "allow_live",
                    "circuit_breaker",
                    "default_policy_version",
                    "created_at",
                    "updated_at",
                }
            }
        )
        if "created_at" in updates:
            provided_created_at = updates["created_at"]
            if provided_created_at is not None and provided_created_at != self.created_at:
                raise ValueError("created_at is immutable")
        self.updated_at = str(_iso_timestamp())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "owner": self.owner,
            "labels": list(self.labels),
            "state": self.state,
            "allow_live": self.allow_live,
            "circuit_breaker": self.circuit_breaker,
            "default_policy_version": self.default_policy_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        payload.update(self.metadata)
        return payload

    @staticmethod
    def _normalize_optional_str(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("expected a string value")
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalize_labels(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, Iterable):
            labels: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    raise ValueError("labels must be strings")
                stripped = item.strip()
                if stripped:
                    labels.append(stripped)
            return labels
        raise ValueError("labels must be a list of strings")

    @staticmethod
    def _normalize_state(value: Any) -> str:
        if value is None:
            return "ACTIVE"
        text = str(value).upper()
        allowed = {"ACTIVE", "SUSPENDED", "DELETED"}
        if text not in allowed:
            raise ValueError("state must be one of ACTIVE, SUSPENDED, DELETED")
        return text


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
class AllocationState:
    """Last known allocation ratios for a world."""

    world_id: str
    allocation: float
    run_id: Optional[str] = None
    etag: Optional[str] = None
    strategy_alloc_total: Dict[str, float] | None = None
    updated_at: Optional[str] = None
    ttl: str | None = None
    stale: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "world_id": self.world_id,
            "allocation": self.allocation,
        }
        if self.run_id is not None:
            data["run_id"] = self.run_id
        if self.etag is not None:
            data["etag"] = self.etag
        if self.updated_at is not None:
            data["updated_at"] = self.updated_at
        if self.strategy_alloc_total is not None:
            data["strategy_alloc_total"] = dict(self.strategy_alloc_total)
        if self.ttl is not None:
            data["ttl"] = self.ttl
        if self.stale:
            data["stale"] = self.stale
        return data


@dataclass
class AllocationRun:
    """Recorded allocation computation keyed by run identifier."""

    run_id: str
    etag: str
    payload: Dict[str, Any]
    executed: bool = False
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "run_id": self.run_id,
            "etag": self.etag,
            "payload": deepcopy(self.payload),
            "executed": self.executed,
        }
        if self.created_at is not None:
            data["created_at"] = self.created_at
        return data


@dataclass
class EvaluationRunRecord:
    """Evaluation run metadata with metrics/validation snapshots."""

    run_id: str
    world_id: str
    strategy_id: str
    stage: str
    risk_tier: str
    model_card_version: str | None = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    validation: Dict[str, Any] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "run_id": self.run_id,
            "world_id": self.world_id,
            "strategy_id": self.strategy_id,
            "stage": self.stage,
            "risk_tier": self.risk_tier,
            "model_card_version": self.model_card_version,
            "metrics": deepcopy(self.metrics),
            "validation": deepcopy(self.validation),
            "summary": deepcopy(self.summary),
        }
        if self.created_at is not None:
            payload["created_at"] = self.created_at
        if self.updated_at is not None:
            payload["updated_at"] = self.updated_at
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "EvaluationRunRecord":
        metrics = payload.get("metrics")
        metrics_dict = dict(metrics) if isinstance(metrics, Mapping) else {}
        validation = payload.get("validation")
        validation_dict = dict(validation) if isinstance(validation, Mapping) else {}
        summary = payload.get("summary")
        summary_dict = dict(summary) if isinstance(summary, Mapping) else {}

        return cls(
            run_id=str(payload["run_id"]),
            world_id=str(payload["world_id"]),
            strategy_id=str(payload["strategy_id"]),
            stage=str(payload.get("stage", "")),
            risk_tier=str(payload.get("risk_tier", "")),
            model_card_version=payload.get("model_card_version"),
            metrics=metrics_dict,
            validation=validation_dict,
            summary=summary_dict,
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
        )


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
    "EvaluationRunRecord",
    "PolicyVersion",
    "ValidationCacheEntry",
    "WorldActivation",
    "WorldAuditLog",
    "WorldNodeRef",
    "WorldPolicies",
    "WorldRecord",
]
