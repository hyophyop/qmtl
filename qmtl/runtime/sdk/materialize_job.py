from __future__ import annotations

"""Compute-only materialization/verification jobs built on SeamlessDataProvider."""

from dataclasses import dataclass, replace, asdict
from typing import Any, Callable, Mapping, MutableMapping
import time
import json
import hashlib
from pathlib import Path
import asyncio

import pandas as pd

from qmtl.foundation.config import SeamlessConfig
from qmtl.runtime.sdk.configuration import get_seamless_config
from qmtl.runtime.sdk.seamless import SeamlessBuilder, build_assembly, hydrate_builder
from qmtl.runtime.sdk.seamless_data_provider import (
    BackfillConfig,
    SeamlessDataProvider,
    SeamlessFetchMetadata,
)
from qmtl.runtime.sdk.conformance import ConformanceReport


@dataclass(slots=True)
class MaterializeReport:
    """Summary of a materialization run."""

    dataset_fingerprint: str | None
    as_of: int | str | None
    coverage_bounds: tuple[int, int] | None
    conformance_flags: dict[str, int]
    conformance_warnings: tuple[str, ...]
    sla_violation: dict[str, Any] | None
    retention_class: str
    retention_ttl_seconds: int | None
    rows: int
    requested_range: tuple[int, int]
    contract_version: str | None
    priority: str | None
    checkpoint_key: str
    resumed: bool
    attempts: int


class MaterializeSeamlessJob:
    """Compute-only materialization helper that reuses the Seamless backfill path."""

    def __init__(
        self,
        *,
        provider: SeamlessDataProvider | None = None,
        preset: str | None = None,
        preset_options: Mapping[str, object] | None = None,
        builder_config: Mapping[str, object] | None = None,
        builder: SeamlessBuilder | None = None,
        start: int | None = None,
        end: int | None = None,
        interval: int = 60,
        node_id: str = "materialize",
        artifact_dir: str | None = None,
        retention_class: str = "research-short",
        retention_ttl_seconds: int | None = None,
        priority: str | None = None,
        contract_version: str | None = None,
        require_live: bool | None = None,
        backfill_config: BackfillConfig | None = None,
        seamless_config: SeamlessConfig | None = None,
        now: Callable[[], float] | None = None,
        checkpoint_dir: str | Path | None = None,
        resume: bool = True,
        max_attempts: int = 1,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        if provider is None and preset is None and builder_config is None and builder is None:
            raise ValueError("provider or preset/builder_config is required")
        if interval <= 0:
            raise ValueError("interval must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")

        self._provider = provider
        self._preset = preset
        self._preset_options: Mapping[str, object] = preset_options or {}
        self._builder_config: Mapping[str, object] = builder_config or {}
        self._builder = builder
        self._start = start
        self._end = end
        self._interval = int(interval)
        self._node_id = node_id
        self._artifact_dir = artifact_dir
        self._retention_class = retention_class
        self._retention_ttl_seconds = retention_ttl_seconds
        self._priority = priority
        self._contract_version = contract_version
        self._require_live = require_live
        self._backfill_config = backfill_config or BackfillConfig()
        self._seamless_config = seamless_config
        self._now = now or time.time
        self._checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self._resume = resume
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds

    async def run(self) -> MaterializeReport:
        """Execute materialization and return a summary report."""

        provider = self._provider or self._build_provider()
        start, end = self._resolve_range(self._start, self._end)
        checkpoint_key = self._compute_checkpoint_key(start, end)

        if self._resume:
            cached = self._maybe_load_checkpoint(checkpoint_key)
            if cached:
                return cached

        self._enforce_live_requirement(provider)
        attempts = 0
        last_exc: Exception | None = None
        while attempts < self._max_attempts:
            attempts += 1
            try:
                result = await provider.fetch(
                    start,
                    end,
                    node_id=self._node_id,
                    interval=self._interval,
                )
                break
            except Exception as exc:  # pragma: no cover - defensive loop guard
                last_exc = exc
                if attempts >= self._max_attempts:
                    raise
                await asyncio.sleep(self._retry_backoff_seconds * attempts)
        else:  # pragma: no cover - defensive, loop always breaks or raises
            if last_exc:
                raise last_exc
            raise RuntimeError("materialize: exhausted attempts without exception")

        metadata = result.metadata
        self._validate_contract(metadata)
        report = provider.last_conformance_report or ConformanceReport()
        materialize_report = MaterializeReport(
            dataset_fingerprint=metadata.dataset_fingerprint,
            as_of=metadata.as_of,
            coverage_bounds=metadata.coverage_bounds,
            conformance_flags=metadata.conformance_flags,
            conformance_warnings=metadata.conformance_warnings,
            sla_violation=metadata.sla_violation,
            retention_class=self._retention_class,
            retention_ttl_seconds=self._retention_ttl_seconds,
            rows=metadata.rows,
            requested_range=metadata.requested_range,
            contract_version=self._contract_version,
            priority=self._priority,
            checkpoint_key=checkpoint_key,
            resumed=False,
            attempts=attempts,
        )
        self._persist_checkpoint(checkpoint_key, materialize_report)
        return materialize_report

    def _build_provider(self) -> SeamlessDataProvider:
        """Hydrate a Seamless provider from presets/builder config."""

        config = self._build_seamless_config()
        assembly = self._build_assembly()
        provider = SeamlessDataProvider(
            cache_source=assembly.cache_source,
            storage_source=assembly.storage_source,
            backfiller=assembly.backfiller,
            live_feed=assembly.live_feed,
            registrar=assembly.registrar,
            backfill_config=self._backfill_config,
            seamless_config=config,
        )
        return provider

    def _build_seamless_config(self) -> SeamlessConfig:
        base = self._seamless_config or get_seamless_config()
        if self._artifact_dir:
            return replace(base, artifact_dir=self._artifact_dir, artifacts_enabled=True)
        return base

    def _build_assembly(self):
        builder = self._builder or SeamlessBuilder()
        config: MutableMapping[str, object] = {}
        config.update(self._builder_config)
        if self._preset:
            config.setdefault("preset", self._preset)
            if self._preset_options:
                config.setdefault("options", self._preset_options)
        assembly = build_assembly(config, builder=builder)
        return assembly

    def _enforce_live_requirement(self, provider: SeamlessDataProvider) -> None:
        requires_live = self._require_live
        if requires_live is None:
            requires_live = bool(self._builder_config.get("live") or self._preset_options.get("live"))
        if requires_live and getattr(provider, "live_feed", None) is None:
            raise ValueError("live feed is required by preset/config but missing")

    def _validate_contract(self, metadata: SeamlessFetchMetadata) -> None:
        if not self._contract_version:
            return
        fingerprint = metadata.dataset_fingerprint
        if fingerprint is None:
            raise ValueError("contract_version provided but dataset_fingerprint is missing")
        tokens = [token for token in str(fingerprint).split(":") if token]
        if self._contract_version not in tokens and fingerprint != self._contract_version:
            raise ValueError(
                f"contract_version '{self._contract_version}' does not match dataset_fingerprint '{fingerprint}'"
            )

    def _resolve_range(self, start: int | None, end: int | None) -> tuple[int, int]:
        resolved_start = int(start if start is not None else self._now())
        resolved_end = int(end if end is not None else self._now())
        if resolved_start > resolved_end:
            raise ValueError("start must be <= end")
        return resolved_start, resolved_end

    def _compute_checkpoint_key(self, start: int, end: int) -> str:
        parts = [
            self._preset or "",
            str(self._builder_config) if self._builder_config else "",
            str(start),
            str(end),
            str(self._interval),
            self._contract_version or "",
            self._retention_class,
            self._priority or "",
        ]
        digest = hashlib.blake2s("|".join(parts).encode("utf-8"), digest_size=12).hexdigest()
        return f"materialize:{digest}"

    def _checkpoint_path(self, key: str) -> Path | None:
        if not self._checkpoint_dir and not self._artifact_dir:
            return None
        base = Path(self._checkpoint_dir or self._artifact_dir or ".").expanduser()
        return base / f"{key}.json"

    def _maybe_load_checkpoint(self, key: str) -> MaterializeReport | None:
        path = self._checkpoint_path(key)
        if not path or not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["checkpoint_key"] = key
            raw["resumed"] = True
            return MaterializeReport(**raw)
        except Exception:
            return None

    def _persist_checkpoint(self, key: str, report: MaterializeReport) -> None:
        path = self._checkpoint_path(key)
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = asdict(report)
            data["resumed"] = report.resumed
            data["checkpoint_key"] = key
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            return


__all__ = ["MaterializeReport", "MaterializeSeamlessJob"]
