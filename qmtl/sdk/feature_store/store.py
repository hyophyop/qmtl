from __future__ import annotations

"""High level orchestration for feature artifact persistence."""

import time
from typing import Any

from .backends import FeatureArtifactBackend, get_backend
from .types import (
    FeatureArtifact,
    FeatureArtifactKey,
    FeatureDescriptor,
    FeatureStoreConfig,
    FeatureStoreContext,
)
from .. import metrics as sdk_metrics


class FeatureArtifactStore:
    """Persist and retrieve immutable feature artifacts."""

    def __init__(
        self,
        backend: FeatureArtifactBackend,
        *,
        retention_versions: int,
        retention_seconds: int | None = None,
    ) -> None:
        self._backend = backend
        self._retention_versions = max(int(retention_versions), 1)
        self._retention_seconds = int(retention_seconds) if retention_seconds else None

    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: FeatureStoreConfig | None = None) -> "FeatureArtifactStore":
        cfg = config or FeatureStoreConfig.from_env()
        backend_cls = get_backend(cfg.backend)
        options = dict(cfg.backend_options or {})
        if cfg.base_path is not None:
            if cfg.backend == "object":
                options.setdefault("cache_dir", cfg.base_path)
            else:
                options.setdefault("base_path", cfg.base_path)
        backend = backend_cls(**options)
        return cls(
            backend,
            retention_versions=cfg.retention_versions,
            retention_seconds=cfg.retention_seconds,
        )

    # ------------------------------------------------------------------
    def write(
        self,
        descriptor: FeatureDescriptor,
        *,
        interval: int | None,
        timestamp: int,
        dataset_fingerprint: str,
        payload: Any,
        context: FeatureStoreContext,
    ) -> FeatureArtifact:
        key = descriptor.materialise_key(
            interval=interval,
            timestamp=timestamp,
            dataset_fingerprint=dataset_fingerprint,
        )
        version = self._next_version(key)
        artifact = FeatureArtifact(
            key=key,
            version=version,
            payload=payload,
            created_at=time.time(),
            execution_domain=context.execution_domain,
            world_id=context.world_id,
        )
        stored = self._backend.write(artifact)
        sdk_metrics.observe_feature_artifact_write(key.factor, context.execution_domain)
        self._apply_retention(
            key,
            max_versions=descriptor.max_versions,
            retention_seconds=descriptor.retention_seconds,
        )
        return stored

    def read_latest(self, key: FeatureArtifactKey, *, context: FeatureStoreContext) -> FeatureArtifact | None:
        versions = self._backend.list_versions(key)
        if not versions:
            sdk_metrics.observe_feature_artifact_miss(key.factor, context.execution_domain)
            return None
        artifact = self._backend.read(key, versions[-1])
        if artifact is None:
            sdk_metrics.observe_feature_artifact_miss(key.factor, context.execution_domain)
            return None
        sdk_metrics.observe_feature_artifact_hit(key.factor, context.execution_domain)
        return artifact

    # ------------------------------------------------------------------
    def _next_version(self, key: FeatureArtifactKey) -> int:
        versions = self._backend.list_versions(key)
        return versions[-1] + 1 if versions else 1

    def _apply_retention(
        self,
        key: FeatureArtifactKey,
        *,
        max_versions: int | None = None,
        retention_seconds: int | None = None,
    ) -> None:
        versions = self._backend.list_versions(key)
        keep = max_versions if max_versions is not None else self._retention_versions
        keep = max(int(keep), 1)
        while len(versions) > keep:
            oldest = versions.pop(0)
            self._backend.delete(key, oldest)
        ttl = retention_seconds if retention_seconds is not None else self._retention_seconds
        if ttl is None:
            return
        cutoff = time.time() - ttl
        for version in list(versions):
            artifact = self._backend.read(key, version)
            if artifact is None:
                continue
            if artifact.created_at < cutoff:
                self._backend.delete(key, version)
                versions.remove(version)


def materialise_key(
    descriptor: FeatureDescriptor,
    *,
    interval: int | None,
    timestamp: int,
    dataset_fingerprint: str,
) -> FeatureArtifactKey:
    return descriptor.materialise_key(
        interval=interval,
        timestamp=timestamp,
        dataset_fingerprint=dataset_fingerprint,
    )


__all__ = [
    "FeatureArtifactStore",
    "materialise_key",
]

