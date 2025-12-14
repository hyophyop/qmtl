"""Risk signal hub for portfolio snapshots and risk signals (in-memory with optional persistence)."""

from __future__ import annotations

import json
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional

from qmtl.services.risk_hub_contract import (
    DEFAULT_REALIZED_RETURNS_MAX_POINTS_PER_SERIES,
    DEFAULT_REALIZED_RETURNS_MAX_POINTS_TOTAL,
    normalize_realized_returns,
    stable_snapshot_hash,
)
from .blob_store import BlobStore


class RiskSnapshotConflictError(RuntimeError):
    """Raised when a snapshot version collides with a different payload."""


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass
class PortfolioSnapshot:
    world_id: str
    as_of: str
    version: str
    weights: Dict[str, float]
    covariance: Dict[str, float] | None = None
    covariance_ref: str | None = None
    realized_returns: Any | None = None
    realized_returns_ref: str | None = None
    stress_ref: str | None = None
    stress: Dict[str, Any] | None = None
    constraints: Dict[str, Any] | None = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    hash: str | None = None
    ttl_sec: int | None = None
    created_at: str = field(default_factory=_iso_now)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "world_id": self.world_id,
            "as_of": self.as_of,
            "version": self.version,
            "weights": dict(self.weights),
            "provenance": dict(self.provenance),
            "created_at": self.created_at,
        }
        if self.covariance:
            payload["covariance"] = dict(self.covariance)
        if self.covariance_ref:
            payload["covariance_ref"] = self.covariance_ref
        if self.realized_returns is not None:
            realized = self.realized_returns
            if isinstance(realized, Mapping):
                payload["realized_returns"] = dict(realized)
            elif isinstance(realized, (list, tuple)):
                payload["realized_returns"] = list(realized)
            else:
                payload["realized_returns"] = realized
        if self.realized_returns_ref:
            payload["realized_returns_ref"] = self.realized_returns_ref
        if self.stress_ref:
            payload["stress_ref"] = self.stress_ref
        if self.stress:
            payload["stress"] = dict(self.stress)
        if self.constraints:
            payload["constraints"] = dict(self.constraints)
        if self.hash:
            payload["hash"] = self.hash
        if self.ttl_sec is not None:
            payload["ttl_sec"] = self.ttl_sec
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PortfolioSnapshot":
        realized = payload.get("realized_returns")
        realized_payload: Any | None
        if isinstance(realized, Mapping):
            realized_payload = dict(realized)
        elif isinstance(realized, (list, tuple)):
            realized_payload = list(realized)
        else:
            realized_payload = realized
        return cls(
            world_id=str(payload["world_id"]),
            as_of=str(payload["as_of"]),
            version=str(payload["version"]),
            weights=dict(payload.get("weights") or {}),
            covariance=dict(payload.get("covariance") or {}) or None,
            covariance_ref=payload.get("covariance_ref"),
            realized_returns=realized_payload,
            realized_returns_ref=payload.get("realized_returns_ref"),
            stress_ref=payload.get("stress_ref"),
            stress=dict(payload.get("stress") or {}) or None,
            constraints=dict(payload.get("constraints") or {}) or None,
            provenance=dict(payload.get("provenance") or {}),
            hash=payload.get("hash"),
            ttl_sec=payload.get("ttl_sec"),
            created_at=str(payload.get("created_at") or _iso_now()),
        )


class RiskSignalHub:
    """Risk snapshot hub with optional persistent backend and cache."""

    def __init__(
        self,
        repository: Any | None = None,
        *,
        max_cached: int | None = 100,
        cache: Any | None = None,
        cache_ttl: int = 300,
        covariance_resolver: Any | None = None,
        blob_store: BlobStore | None = None,
        inline_cov_threshold: int = 100,
        ttl_sec_default: int = 900,
        ttl_sec_max: int = 86400,
    ) -> None:
        self._snapshots: Dict[str, List[PortfolioSnapshot]] = {}
        self._repository = repository
        self._max_cached = max_cached
        self._cache = cache
        self._cache_ttl = cache_ttl
        self._covariance_resolver = covariance_resolver
        self._blob_store = blob_store
        self._inline_cov_threshold = inline_cov_threshold
        self._ttl_sec_default = int(ttl_sec_default)
        self._ttl_sec_max = int(ttl_sec_max)
        self._logger = logging.getLogger(__name__)

    def bind_repository(self, repository: Any | None) -> None:
        """Attach or replace a persistent repository."""
        self._repository = repository

    def bind_cache(self, cache: Any | None, *, ttl: int | None = None) -> None:
        """Attach or replace a cache client (e.g., Redis)."""
        self._cache = cache
        if ttl is not None:
            self._cache_ttl = ttl

    def bind_covariance_resolver(self, resolver: Any | None) -> None:
        """Attach a resolver for covariance_ref → covariance materialization."""
        self._covariance_resolver = resolver

    def bind_blob_store(self, store: BlobStore | None) -> None:
        """Attach a blob store to offload large payloads (covariance/returns/stress)."""
        self._blob_store = store

    async def resolve_blob_ref(self, ref: str) -> Any | None:
        """Resolve a blob-store reference into an in-memory payload.

        This is used for large optional fields such as realized returns or stress
        results that are transmitted by reference.
        """

        if not ref or self._blob_store is None:
            return None
        resolver = self._blob_store.read
        try:
            result = resolver(ref)
            if asyncio.iscoroutine(result):  # type: ignore[attr-defined]
                result = await result  # type: ignore[assignment]
            return result
        except Exception:
            self._logger.exception("Failed to resolve blob ref=%s", ref)
            return None

    async def upsert_snapshot(self, snapshot: PortfolioSnapshot) -> bool:
        self._validate_snapshot(snapshot)
        if snapshot.ttl_sec is None:
            snapshot.ttl_sec = self._ttl_sec_default
        ttl_value = int(snapshot.ttl_sec)
        if ttl_value <= 0:
            raise ValueError("ttl_sec must be positive")
        if ttl_value > self._ttl_sec_max:
            raise ValueError(f"ttl_sec must be <= {self._ttl_sec_max}")

        snapshot = self._maybe_offload_covariance(snapshot)
        snapshot = self._maybe_offload_auxiliary(snapshot)
        snapshot = self._with_hash(snapshot)

        if self._expired(snapshot):
            raise ValueError("snapshot is expired")

        deduped = await self._enforce_version_idempotency(snapshot)
        deduped = self._cache_snapshot(snapshot) or deduped
        await self._cache_latest(snapshot)
        if self._repository is None:
            return deduped
        try:
            await self._repository.upsert(snapshot.world_id, snapshot.to_dict())  # type: ignore[union-attr]
        except Exception:
            self._logger.exception("Failed to persist risk snapshot for %s", snapshot.world_id)
        return deduped

    async def latest_snapshot(self, world_id: str) -> Optional[PortfolioSnapshot]:
        cached_snap = await self._cached_latest(world_id)
        if cached_snap:
            return await self._maybe_materialize_covariance(cached_snap)
        cached = self._snapshots.get(world_id, [])
        if cached:
            snap = self._latest_fresh(cached)
            if snap:
                return await self._maybe_materialize_covariance(snap)
        if self._repository is None:
            return None
        try:
            payload = await self._repository.latest(world_id)  # type: ignore[union-attr]
            if payload:
                snapshot = PortfolioSnapshot.from_payload(payload)
                self._cache_snapshot(snapshot)
                fresh = self._latest_fresh(self._snapshots.get(world_id, []))
                return await self._maybe_materialize_covariance(fresh) if fresh else None
        except Exception:
            self._logger.exception("Failed to load latest risk snapshot for %s", world_id)
        return None

    async def get_snapshot(
        self,
        world_id: str,
        *,
        version: str | None = None,
        as_of: str | None = None,
    ) -> Optional[PortfolioSnapshot]:
        if version:
            for snap in reversed(self._snapshots.get(world_id, [])):
                if snap.version == version and not self._expired(snap):
                    return await self._maybe_materialize_covariance(snap)
            if self._repository is not None:
                getter = getattr(self._repository, "get", None)
                if getter is not None:
                    payload = await getter(world_id, version)
                    if payload:
                        snap = PortfolioSnapshot.from_payload(payload)
                        self._cache_snapshot(snap)
                        if not self._expired(snap):
                            return await self._maybe_materialize_covariance(snap)
            return None

        if as_of:
            return await self.snapshot_for_as_of(world_id, as_of)
        return await self.latest_snapshot(world_id)

    async def list_snapshots(self, world_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        entries = self._snapshots.get(world_id, [])
        if (not entries or len(entries) < limit) and self._repository is not None:
            try:
                rows = await self._repository.list(world_id, limit=limit)  # type: ignore[union-attr]
                for payload in rows:
                    self._cache_snapshot(PortfolioSnapshot.from_payload(payload))
            except Exception:
                self._logger.exception("Failed to list risk snapshots for %s", world_id)
        entries = self._snapshots.get(world_id, [])
        return [s.to_dict() for s in entries[-limit:] if not self._expired(s)]

    async def snapshot_for_as_of(self, world_id: str, as_of: str) -> Optional[PortfolioSnapshot]:
        entries = self._snapshots.get(world_id, [])
        if not entries and self._repository is not None:
            try:
                rows = await self._repository.list(world_id, limit=50)  # type: ignore[union-attr]
                for payload in rows:
                    self._cache_snapshot(PortfolioSnapshot.from_payload(payload))
                entries = self._snapshots.get(world_id, [])
            except Exception:
                self._logger.exception("Failed to fetch historical snapshots for %s", world_id)
        for snap in reversed(entries):
            if snap.as_of <= as_of and not self._expired(snap):
                return await self._maybe_materialize_covariance(snap)
        return None

    def _cache_snapshot(self, snapshot: PortfolioSnapshot) -> bool:
        entries = self._snapshots.setdefault(snapshot.world_id, [])
        existing = next((s for s in entries if s.version == snapshot.version), None)
        if existing is not None:
            if (existing.hash or "") == (snapshot.hash or ""):
                return True
            raise RiskSnapshotConflictError(
                f"snapshot version collision for world_id={snapshot.world_id} version={snapshot.version}"
            )
        entries.append(snapshot)
        entries.sort(key=lambda s: (s.as_of, s.version))
        if self._max_cached is not None and len(entries) > self._max_cached:
            entries = entries[-self._max_cached :]
        self._snapshots[snapshot.world_id] = entries
        return False

    def _validate_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        if not snapshot.world_id:
            raise ValueError("world_id is required")
        if not snapshot.as_of:
            raise ValueError("as_of is required")
        if not snapshot.version:
            raise ValueError("version is required")
        if not snapshot.weights:
            raise ValueError("weights are required")
        weight_sum = sum(snapshot.weights.values())
        if weight_sum <= 0:
            raise ValueError("weights must sum to positive value")
        if abs(weight_sum - 1.0) > 1e-3:
            # allow slight drift but enforce normalized input
            raise ValueError("weights must sum to ~1.0")
        _ = self._parse_iso(snapshot.as_of)  # raises on invalid
        if snapshot.realized_returns_ref is not None:
            if not isinstance(snapshot.realized_returns_ref, str) or not snapshot.realized_returns_ref.strip():
                raise ValueError("realized_returns_ref must be a non-empty string when provided")
            snapshot.realized_returns_ref = snapshot.realized_returns_ref.strip()
        if snapshot.realized_returns is not None:
            snapshot.realized_returns = normalize_realized_returns(
                snapshot.realized_returns,
                max_points_per_series=DEFAULT_REALIZED_RETURNS_MAX_POINTS_PER_SERIES,
                max_points_total=DEFAULT_REALIZED_RETURNS_MAX_POINTS_TOTAL,
            )

    @staticmethod
    def _with_hash(snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        if snapshot.hash:
            return snapshot
        snapshot.hash = stable_snapshot_hash(snapshot.to_dict())
        return snapshot

    def _expired(self, snap: PortfolioSnapshot) -> bool:
        if snap.ttl_sec is None:
            return False
        created = self._parse_iso(snap.created_at)
        if created is None:
            return False
        return datetime.now(timezone.utc) > created + timedelta(seconds=int(snap.ttl_sec))

    def _latest_fresh(self, entries: List[PortfolioSnapshot]) -> Optional[PortfolioSnapshot]:
        for snap in reversed(entries):
            if not self._expired(snap):
                return snap
        return None

    async def _cache_latest(self, snapshot: PortfolioSnapshot) -> None:
        if self._cache is None:
            return
        ttl = snapshot.ttl_sec if snapshot.ttl_sec is not None else self._cache_ttl
        if ttl is None or ttl <= 0:
            return
        key = f"risk-hub:{snapshot.world_id}:latest"
        try:
            await self._cache.set(key, json.dumps(snapshot.to_dict()))
            await self._cache.expire(key, int(ttl))
        except Exception:
            self._logger.exception("Failed to cache snapshot for %s", snapshot.world_id)

    async def _cached_latest(self, world_id: str) -> Optional[PortfolioSnapshot]:
        if self._cache is None:
            return None
        key = f"risk-hub:{world_id}:latest"
        try:
            raw = await self._cache.get(key)
            if not raw:
                return None
            payload = json.loads(raw)
            snap = PortfolioSnapshot.from_payload(payload)
            if self._expired(snap):
                return None
            return snap
        except Exception:
            return None

    async def _maybe_materialize_covariance(
        self, snapshot: PortfolioSnapshot | None
    ) -> Optional[PortfolioSnapshot]:
        if snapshot is None:
            return None
        if snapshot.covariance or not snapshot.covariance_ref:
            return snapshot
        resolver = self._covariance_resolver
        # blob_store fallback
        if resolver is None and self._blob_store is not None:
            resolver = self._blob_store.read
        if resolver is None:
            return snapshot
        try:
            result = resolver(snapshot.covariance_ref)
            if asyncio.iscoroutine(result):  # type: ignore[attr-defined]
                result = await result  # type: ignore[assignment]
            if isinstance(result, Mapping):
                snapshot.covariance = dict(result)
        except Exception:
            self._logger.exception("Failed to resolve covariance_ref=%s", snapshot.covariance_ref)
        return snapshot

    def _maybe_offload_covariance(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        if snapshot.covariance and self._blob_store and self._inline_cov_threshold is not None:
            if len(snapshot.covariance) > self._inline_cov_threshold and not snapshot.covariance_ref:
                ref = self._blob_store.write(snapshot.version or "cov", snapshot.covariance)
                snapshot = PortfolioSnapshot.from_payload(
                    {
                        **snapshot.to_dict(),
                        "covariance": None,
                        "covariance_ref": ref,
                    }
                )
        return snapshot

    def _maybe_offload_auxiliary(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        if self._blob_store is None or self._inline_cov_threshold is None:
            return snapshot

        payload = snapshot.to_dict()
        version = str(payload.get("version") or "snapshot")
        changed = False

        realized = payload.get("realized_returns")
        if payload.get("realized_returns_ref") is None and realized is not None:
            threshold = int(self._inline_cov_threshold)
            points = self._realized_returns_points(realized)
            if points is None:
                points = len(realized) if isinstance(realized, Mapping) else None
            if points is not None and points > threshold:
                ref = self._blob_store.write(f"{version}-realized", realized)
                payload["realized_returns_ref"] = ref
                payload.pop("realized_returns", None)
                changed = True

        stress = payload.get("stress")
        if payload.get("stress_ref") is None and isinstance(stress, Mapping):
            if len(stress) > self._inline_cov_threshold:
                ref = self._blob_store.write(f"{version}-stress", stress)
                payload["stress_ref"] = ref
                payload.pop("stress", None)
                changed = True

        return PortfolioSnapshot.from_payload(payload) if changed else snapshot

    @staticmethod
    def _realized_returns_points(realized: Any) -> int | None:
        if isinstance(realized, Mapping):
            total = 0
            for value in realized.values():
                if isinstance(value, (list, tuple)):
                    total += len(value)
            return total if total else None
        if isinstance(realized, (list, tuple)):
            return len(realized)
        return None

    async def _enforce_version_idempotency(self, snapshot: PortfolioSnapshot) -> bool:
        if self._repository is None:
            return False
        getter = getattr(self._repository, "get", None)
        if getter is None:
            return False
        try:
            existing = await getter(snapshot.world_id, snapshot.version)
        except Exception:
            return False
        if not existing:
            return False
        existing_hash = str(existing.get("hash") or "")
        incoming_hash = str(snapshot.hash or "")
        if existing_hash and existing_hash == incoming_hash:
            return True
        raise RiskSnapshotConflictError(
            f"snapshot version collision for world_id={snapshot.world_id} version={snapshot.version}"
        )

    @staticmethod
    def _parse_iso(value: str | None) -> datetime | None:
        if not value:
            return None
        text = str(value)
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None


__all__ = ["RiskSignalHub", "PortfolioSnapshot", "RiskSnapshotConflictError", "stable_snapshot_hash"]
