from __future__ import annotations

"""High level helpers for interacting with feature artifact storage."""

import logging
from typing import Any, Iterable, Sequence

from qmtl.foundation.common.compute_key import DEFAULT_EXECUTION_DOMAIN

from .base import FeatureArtifactKey, FeatureStoreBackend
from .filesystem import FileSystemFeatureStore
from .. import configuration

logger = logging.getLogger(__name__)


def _infer_instrument(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("instrument", "symbol", "ticker"):
            value = payload.get(key)
            if value is not None:
                return str(value)
    for attr in ("instrument", "symbol", "ticker"):
        if hasattr(payload, attr):
            value = getattr(payload, attr)
            if value is not None:
                return str(value)
    return "__default__"


class FeatureArtifactPlane:
    """Facade coordinating artifact writes and reads for the SDK."""

    def __init__(
        self,
        backend: FeatureStoreBackend,
        *,
        write_domains: Iterable[str] | None = None,
    ) -> None:
        self.backend = backend
        self.write_domains = {d for d in (write_domains or ("backtest", "dryrun"))}
        self._dataset_fingerprint: str | None = None
        self._execution_domain: str = DEFAULT_EXECUTION_DOMAIN

    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls) -> FeatureArtifactPlane | None:
        cfg = configuration.cache_config()
        if not cfg.feature_artifacts_enabled:
            return None

        base = cfg.feature_artifact_dir
        max_versions = cfg.feature_artifact_versions
        if max_versions is not None:
            try:
                max_versions = int(max_versions)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                logger.warning(
                    "invalid feature_artifact_versions value in configuration: %s",
                    max_versions,
                )
                max_versions = None

        backend = FileSystemFeatureStore(base, max_versions=max_versions)
        domains: Sequence[str] | None = None
        if cfg.feature_artifact_write_domains:
            domains = [str(d).strip() for d in cfg.feature_artifact_write_domains if str(d).strip()]
        return cls(backend, write_domains=domains)

    # ------------------------------------------------------------------
    def configure(
        self,
        *,
        dataset_fingerprint: str | None = None,
        execution_domain: str | None = None,
    ) -> None:
        if dataset_fingerprint is not None:
            self._dataset_fingerprint = dataset_fingerprint
        if execution_domain is not None:
            self._execution_domain = execution_domain or DEFAULT_EXECUTION_DOMAIN

    # ------------------------------------------------------------------
    def _resolve_factor(self, factor: Any) -> tuple[str, int, str]:
        if hasattr(factor, "node_id"):
            node = factor
            factor_id = getattr(node, "node_id")
            interval = int(getattr(node, "interval", 0) or 0)
            params = getattr(node, "config_hash", "")
        else:
            raise ValueError("factor must be a Node when using artifact helpers")
        return str(factor_id), interval, str(params)

    def _resolve_dataset_fingerprint(self, factor: Any, override: str | None) -> str | None:
        if override is not None:
            return override
        if hasattr(factor, "dataset_fingerprint"):
            value = getattr(factor, "dataset_fingerprint")
            if value:
                return str(value)
        return self._dataset_fingerprint

    def load_series(
        self,
        factor: Any,
        *,
        instrument: str | None = None,
        dataset_fingerprint: str | None = None,
        start: int | None = None,
        end: int | None = None,
    ) -> list[tuple[int, Any]]:
        factor_id, interval, params = self._resolve_factor(factor)
        dataset = self._resolve_dataset_fingerprint(factor, dataset_fingerprint)
        if dataset is None:
            return []
        inst = instrument or "__default__"
        return self.backend.load_series(
            factor=factor_id,
            interval=interval,
            params=params,
            instrument=inst,
            dataset_fingerprint=dataset,
            start=start,
            end=end,
        )

    def list_instruments(
        self,
        factor: Any,
        *,
        dataset_fingerprint: str | None = None,
    ) -> Iterable[str]:
        factor_id, _interval, params = self._resolve_factor(factor)
        dataset = self._resolve_dataset_fingerprint(factor, dataset_fingerprint)
        if dataset is None:
            return []
        return self.backend.list_instruments(
            factor=factor_id,
            params=params,
            dataset_fingerprint=dataset,
        )

    def count(
        self,
        factor: Any,
        *,
        instrument: str | None = None,
        dataset_fingerprint: str | None = None,
    ) -> int:
        factor_id, interval, params = self._resolve_factor(factor)
        dataset = self._resolve_dataset_fingerprint(factor, dataset_fingerprint)
        if dataset is None:
            return 0
        inst = instrument or "__default__"
        return self.backend.count(
            factor=factor_id,
            interval=interval,
            params=params,
            instrument=inst,
            dataset_fingerprint=dataset,
        )

    # ------------------------------------------------------------------
    def record(self, factor: Any, timestamp: int, payload: Any) -> None:
        if payload is None:
            return
        try:
            node = factor
            enabled = bool(getattr(node, "enable_feature_artifacts", False))
        except Exception:
            enabled = False
        if not enabled:
            return
        dataset = self._resolve_dataset_fingerprint(factor, None)
        if not dataset:
            return
        node_domain = str(getattr(factor, "execution_domain", DEFAULT_EXECUTION_DOMAIN))
        if self.write_domains and node_domain not in self.write_domains:
            return
        factor_id, interval, params = self._resolve_factor(factor)
        instrument = _infer_instrument(payload)
        key = FeatureArtifactKey(
            factor=factor_id,
            interval=interval,
            params=params,
            instrument=instrument,
            timestamp=int(timestamp),
            dataset_fingerprint=dataset,
        )
        try:
            self.backend.write(key, payload)
        except Exception:
            logger.exception("failed to write feature artifact for factor %s", factor_id)

