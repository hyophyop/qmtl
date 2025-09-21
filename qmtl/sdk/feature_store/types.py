from __future__ import annotations

"""Dataclasses shared by the Feature Artifact Plane implementation."""

import json
import os
from dataclasses import dataclass, field, replace
from typing import Any, Mapping


def _stable_params(params: Mapping[str, Any] | None) -> str:
    """Return a canonical JSON representation for ``params``."""

    if params is None:
        return "{}"
    if not isinstance(params, Mapping):
        raise TypeError("feature params must be a mapping of string keys")
    try:
        return json.dumps(params, sort_keys=True, separators=(",", ":"))
    except TypeError as exc:  # pragma: no cover - defensive guard
        raise TypeError("feature params must be JSON serialisable") from exc


@dataclass(frozen=True)
class FeatureDescriptor:
    """Static description attached to a :class:`qmtl.sdk.node.Node`.

    The descriptor encodes how the node should materialise its feature
    artifact.  The dataset fingerprint is optional at definition time – it is
    typically provided by the Runner based on the execution domain.
    """

    factor: str
    instrument: str
    params: Mapping[str, Any] | None = field(default_factory=dict)
    interval: int | None = None
    dataset_fingerprint: str | None = None
    max_versions: int | None = None
    retention_seconds: int | None = None

    @classmethod
    def coerce(cls, value: FeatureDescriptor | Mapping[str, Any] | None) -> FeatureDescriptor | None:
        if value is None:
            return None
        if isinstance(value, FeatureDescriptor):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("feature_plane must be a mapping or FeatureDescriptor")
        data = dict(value)
        factor = data.get("factor")
        instrument = data.get("instrument")
        if not isinstance(factor, str) or not factor:
            raise ValueError("feature_plane.factor must be a non-empty string")
        if not isinstance(instrument, str) or not instrument:
            raise ValueError("feature_plane.instrument must be a non-empty string")
        params = data.get("params") or {}
        interval = data.get("interval")
        dataset_fp = data.get("dataset_fingerprint")
        max_versions = data.get("max_versions")
        retention_seconds = data.get("retention_seconds")
        return cls(
            factor=factor,
            instrument=instrument,
            params=params,
            interval=int(interval) if interval is not None else None,
            dataset_fingerprint=str(dataset_fp) if dataset_fp is not None else None,
            max_versions=int(max_versions) if max_versions is not None else None,
            retention_seconds=int(retention_seconds)
            if retention_seconds is not None
            else None,
        )

    def with_interval(self, interval: int | None) -> FeatureDescriptor:
        if interval is None or interval == self.interval:
            return self
        return replace(self, interval=int(interval))

    def with_dataset_fingerprint(self, dataset_fingerprint: str | None) -> FeatureDescriptor:
        if dataset_fingerprint is None:
            return self
        return replace(self, dataset_fingerprint=str(dataset_fingerprint))

    def materialise_key(
        self,
        *,
        interval: int | None,
        timestamp: int,
        dataset_fingerprint: str,
    ) -> "FeatureArtifactKey":
        interval_val = int(interval or self.interval or 0)
        bucket = timestamp - (timestamp % (interval_val or 1))
        return FeatureArtifactKey(
            factor=self.factor,
            interval=interval_val,
            params=_stable_params(self.params),
            instrument=self.instrument,
            timestamp=bucket,
            dataset_fingerprint=str(dataset_fingerprint),
        )


@dataclass(frozen=True)
class FeatureArtifactKey:
    """Identifier for an immutable feature artifact."""

    factor: str
    interval: int
    params: str
    instrument: str
    timestamp: int
    dataset_fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "interval": self.interval,
            "params": self.params,
            "instrument": self.instrument,
            "timestamp": self.timestamp,
            "dataset_fingerprint": self.dataset_fingerprint,
        }


@dataclass(frozen=True)
class FeatureArtifact:
    """Concrete persisted artifact payload."""

    key: FeatureArtifactKey
    version: int
    payload: Any
    created_at: float
    execution_domain: str
    world_id: str | None = None
    encoding: str = "json"


@dataclass
class FeatureStoreConfig:
    """Runtime configuration for the :class:`FeatureArtifactStore`."""

    backend: str = "local"
    base_path: str | None = None
    retention_versions: int = 3
    retention_seconds: int | None = None
    backend_options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "FeatureStoreConfig":
        backend = os.getenv("QMTL_FEATURE_STORE_BACKEND", "local").strip() or "local"
        base_path = os.getenv("QMTL_FEATURE_STORE_DIR")
        max_versions = os.getenv("QMTL_FEATURE_STORE_MAX_VERSIONS")
        ttl = os.getenv("QMTL_FEATURE_STORE_TTL_SECONDS")
        retention_versions = int(max_versions) if max_versions else 3
        retention_seconds = int(ttl) if ttl else None
        return cls(
            backend=backend,
            base_path=base_path,
            retention_versions=retention_versions,
            retention_seconds=retention_seconds,
        )


@dataclass
class FeatureStoreContext:
    """Execution-scoped context controlling artifact behaviour."""

    execution_domain: str
    dataset_fingerprint: str | None = None
    world_id: str | None = None

    def is_writer(self) -> bool:
        return self.execution_domain in {"backtest", "dryrun"}


__all__ = [
    "FeatureArtifact",
    "FeatureArtifactKey",
    "FeatureDescriptor",
    "FeatureStoreConfig",
    "FeatureStoreContext",
]

