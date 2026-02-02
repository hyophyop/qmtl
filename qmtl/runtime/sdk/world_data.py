from __future__ import annotations

"""Helpers for world → data preset auto-wiring."""

import logging
import math
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence, cast

import numpy as np
import polars as pl

from qmtl.foundation.config import SeamlessConfig
from qmtl.runtime.sdk.configuration import get_seamless_config
from qmtl.runtime.sdk.seamless.builder import SeamlessBuilder, SeamlessPresetRegistry
from qmtl.runtime.sdk.seamless_data_provider import (
    BackfillConfig,
    DataAvailabilityStrategy,
    SeamlessDataProvider,
    _load_presets_document,
)
from qmtl.runtime.io.seamless_provider import _FrameMappingDataSource

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DataPresetSpec:
    key: str
    interval_ms: int | None
    stabilization_bars: int | None
    sla_preset: str | None
    conformance_preset: str | None
    provider_name: str | None
    provider_options: dict[str, Any]
    source: str | None


@dataclass(slots=True)
class WorldDataSelection:
    world_preset_id: str
    data_preset_key: str
    world_entry: Mapping[str, Any]
    spec: DataPresetSpec
    source: str | None


@dataclass(slots=True)
class ProviderBinding:
    provider: SeamlessDataProvider
    spec: DataPresetSpec
    seed_node: Callable[[Any, int | None], None] | None
    dataset_fingerprint: str | None
    max_lag_seconds: float | None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _duration_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
        except Exception:
            return None
        if math.isnan(numeric):
            return None
        return numeric
    if isinstance(value, str):
        raw = value.strip().lower()
        if not raw:
            return None
        multipliers = {
            "ms": 0.001,
            "s": 1.0,
            "m": 60.0,
            "h": 3600.0,
            "d": 86400.0,
        }
        for suffix, factor in multipliers.items():
            if raw.endswith(suffix):
                try:
                    return float(raw[: -len(suffix)]) * factor
                except Exception:
                    return None
        try:
            return float(raw)
        except Exception:
            return None
    return None


def _interval_to_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
        except Exception:
            return None
        if math.isnan(numeric):
            return None
        return int(numeric * 1000)
    if isinstance(value, str):
        raw = value.strip().lower()
        if not raw:
            return None
        if raw.endswith("ms"):
            try:
                return int(float(raw[:-2]))
            except Exception:
                return None
        if raw.endswith("s"):
            try:
                return int(float(raw[:-1]) * 1000)
            except Exception:
                return None
        if raw.endswith("m"):
            try:
                return int(float(raw[:-1]) * 60_000)
            except Exception:
                return None
        if raw.endswith("h"):
            try:
                return int(float(raw[:-1]) * 3_600_000)
            except Exception:
                return None
        try:
            return int(float(raw) * 1000)
        except Exception:
            return None
    return None


def _world_payload(world_description: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not isinstance(world_description, Mapping):
        return None
    if "world" in world_description and isinstance(world_description["world"], Mapping):
        return world_description["world"]
    return world_description


def _select_world_data_entry(
    world: Mapping[str, Any],
    *,
    preferred_id: str | None,
    world_id: str,
) -> tuple[str, Mapping[str, Any]]:
    data_section = _as_mapping(world.get("data"))
    presets = _as_sequence(data_section.get("presets"))
    entries: list[Mapping[str, Any]] = [
        entry for entry in presets if isinstance(entry, Mapping)
    ]
    if not entries:
        raise ValueError(f"world '{world_id}' does not define data.presets for StreamInput auto-wiring")

    if preferred_id:
        for entry in entries:
            candidate = entry.get("id") or entry.get("preset")
            if str(candidate) == preferred_id:
                return str(candidate), entry
        raise ValueError(
            f"world '{world_id}' has no data preset with id '{preferred_id}'"
        )

    entry = entries[0]
    preset_id = entry.get("id") or entry.get("preset")
    if not preset_id:
        raise ValueError(f"world '{world_id}' data preset is missing 'id'")
    return str(preset_id), entry


def _load_data_preset_spec(
    preset_key: str,
    *,
    seamless_config: SeamlessConfig,
) -> DataPresetSpec:
    presets_data, source = _load_presets_document(seamless_config)
    data_presets = presets_data.get("data_presets") if isinstance(presets_data, dict) else None
    if not isinstance(data_presets, Mapping):
        raise ValueError("data_presets map is missing from Seamless presets document")
    raw_spec = _as_mapping(data_presets.get(preset_key))
    if not raw_spec:
        raise ValueError(f"data preset '{preset_key}' not found in presets document")

    provider_block = _as_mapping(raw_spec.get("provider"))
    provider_name = provider_block.get("preset") or provider_block.get("name")
    provider_options = dict(_as_mapping(provider_block.get("options")))

    return DataPresetSpec(
        key=preset_key,
        interval_ms=_int_or_none(raw_spec.get("interval_ms")),
        stabilization_bars=_int_or_none(raw_spec.get("stabilization_bars")),
        sla_preset=raw_spec.get("sla_preset"),
        conformance_preset=raw_spec.get("conformance_preset"),
        provider_name=str(provider_name) if provider_name else None,
        provider_options=provider_options,
        source=source,
    )


def resolve_world_data_selection(
    *,
    world_description: Mapping[str, Any] | None,
    world_id: str,
    data_preset_id: str | None,
    seamless_config: SeamlessConfig | None = None,
) -> WorldDataSelection | None:
    world = _world_payload(world_description)
    if world is None:
        return None

    preset_id, world_entry = _select_world_data_entry(world, preferred_id=data_preset_id, world_id=world_id)
    config = seamless_config or get_seamless_config()
    spec = _load_data_preset_spec(str(world_entry.get("preset") or preset_id), seamless_config=config)
    return WorldDataSelection(
        world_preset_id=str(preset_id),
        data_preset_key=spec.key,
        world_entry=world_entry,
        spec=spec,
        source=spec.source,
    )


def _apply_world_overrides(
    spec: DataPresetSpec,
    world_entry: Mapping[str, Any],
    base_config: SeamlessConfig,
) -> tuple[SeamlessConfig, BackfillConfig, int | None, float | None, str | None]:
    seamless_cfg = replace(base_config)
    overrides = _as_mapping(world_entry.get("seamless"))
    window = _as_mapping(world_entry.get("window"))
    live = _as_mapping(world_entry.get("live"))

    if spec.sla_preset:
        seamless_cfg.sla_preset = spec.sla_preset
    if spec.conformance_preset:
        seamless_cfg.conformance_preset = spec.conformance_preset
    if overrides.get("sla_preset"):
        seamless_cfg.sla_preset = str(overrides["sla_preset"])
    if overrides.get("conformance_preset"):
        seamless_cfg.conformance_preset = str(overrides["conformance_preset"])

    stabilization = _int_or_none(overrides.get("stabilization_bars")) or spec.stabilization_bars
    stabilization = _int_or_none(stabilization)

    backfill_mode = overrides.get("backfill_mode") or spec.provider_options.get("backfill_mode")
    mode_value: Literal["background", "sync"] = "background"
    if isinstance(backfill_mode, str) and backfill_mode in ("background", "sync"):
        mode_value = cast(Literal["background", "sync"], backfill_mode)
    backfill_window = _int_or_none(window.get("warmup_bars") or spec.provider_options.get("warmup_bars"))
    backfill_cfg = BackfillConfig(
        mode=mode_value,
        window_bars=backfill_window or BackfillConfig().window_bars,
    )
    max_lag_seconds = _duration_seconds(live.get("max_lag"))
    dataset_fp = str(world_entry.get("fingerprint")) if world_entry.get("fingerprint") else None
    return seamless_cfg, backfill_cfg, stabilization, max_lag_seconds, dataset_fp


def _build_provider_from_spec(
    selection: WorldDataSelection,
    *,
    base_config: SeamlessConfig,
) -> ProviderBinding:
    spec = selection.spec
    config, backfill_cfg, stabilization_bars, max_lag_seconds, dataset_fp = _apply_world_overrides(
        spec, selection.world_entry, base_config
    )

    provider_name = spec.provider_name or "demo.inmemory.ohlcv"
    options = dict(spec.provider_options)
    universe = _as_mapping(selection.world_entry.get("universe"))
    if universe and universe.get("symbols") and "symbols" not in options:
        options["symbols"] = universe.get("symbols")
    if universe and universe.get("venue") and "exchange_id" not in options:
        options["exchange_id"] = universe.get("venue")

    if provider_name in {"demo.inmemory.ohlcv", "inmemory"}:
        source = _FrameMappingDataSource()

        def _seed(node: Any, interval_ms: int | None) -> None:
            interval_value = interval_ms or spec.interval_ms or 60_000
            bars = _int_or_none(options.get("bars")) or 360
            seed = _int_or_none(options.get("seed")) or 7
            frame = _generate_demo_ohlcv_frame(
                bars=bars,
                interval_ms=interval_value,
                seed=seed,
                symbols=_as_sequence(options.get("symbols")) or None,
            )
            source.register(node_id=getattr(node, "node_id", ""), interval=int(interval_value / 1000), frame=frame)

        provider = SeamlessDataProvider(
            cache_source=None,
            storage_source=source,
            backfiller=None,
            live_feed=None,
            stabilization_bars=stabilization_bars or 0,
            backfill_config=backfill_cfg,
            partial_ok=True,
            seamless_config=config,
        )
        return ProviderBinding(
            provider=provider,
            spec=spec,
            seed_node=_seed,
            dataset_fingerprint=dataset_fp or f"data_preset:{spec.key}",
            max_lag_seconds=max_lag_seconds,
        )

    builder: SeamlessBuilder
    try:
        builder = SeamlessPresetRegistry.apply(provider_name, builder=None, config=options)
    except Exception as exc:  # pragma: no cover - config errors surface to caller
        raise ValueError(f"failed to apply seamless preset '{provider_name}': {exc}") from exc
    assembly = builder.build()
    provider = SeamlessDataProvider(
        cache_source=assembly.cache_source,
        storage_source=assembly.storage_source,
        backfiller=assembly.backfiller,
        live_feed=assembly.live_feed,
        registrar=assembly.registrar,
        stabilization_bars=stabilization_bars or 0,
        backfill_config=backfill_cfg,
        seamless_config=config,
    )
    return ProviderBinding(
        provider=provider,
        spec=spec,
        seed_node=None,
        dataset_fingerprint=dataset_fp or f"data_preset:{spec.key}",
        max_lag_seconds=max_lag_seconds,
    )


def build_provider_binding(
    selection: WorldDataSelection,
    *,
    base_config: SeamlessConfig | None = None,
) -> ProviderBinding:
    return _build_provider_from_spec(selection, base_config=base_config or get_seamless_config())


def _stream_inputs(strategy: Any) -> Iterable[Any]:
    from qmtl.runtime.sdk import StreamInput

    return (node for node in getattr(strategy, "nodes", []) if isinstance(node, StreamInput))


def apply_data_binding(
    binding: ProviderBinding,
    *,
    strategy: Any,
    world_id: str,
) -> int:
    attached = 0
    for node in _stream_inputs(strategy):
        if getattr(node, "history_provider", None) is not None:
            continue
        interval_ms = _interval_to_ms(getattr(node, "interval", None))
        if binding.spec.interval_ms and interval_ms and binding.spec.interval_ms != interval_ms:
            raise ValueError(
                f"world '{world_id}' data preset '{binding.spec.key}' interval {binding.spec.interval_ms}ms "
                f"does not match StreamInput '{getattr(node, 'node_id', '<unknown>')}' interval {interval_ms}ms"
            )
        if binding.seed_node:
            try:
                binding.seed_node(node, interval_ms or binding.spec.interval_ms)
            except Exception as exc:
                logger.debug("world_data.seed_failed", exc_info=True, extra={"error": str(exc)})
        setattr(node, "_history_provider", binding.provider)
        try:
            binding.provider.bind_stream(node)
        except Exception:
            logger.debug("world_data.bind_failed", exc_info=True)
        if binding.dataset_fingerprint:
            try:
                node.dataset_fingerprint = binding.dataset_fingerprint
            except Exception:
                logger.debug("world_data.fingerprint_ignored", exc_info=True)
        attached += 1
    if attached:
        setattr(strategy, "_world_data_provider", binding.provider)
    return attached


def _generate_demo_ohlcv_frame(
    *,
    bars: int,
    interval_ms: int,
    seed: int,
    symbols: Sequence[Any] | None,
) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    interval_sec = max(1, int(interval_ms / 1000))
    now_bucket = int(time.time()) // interval_sec * interval_sec
    start_ts = now_bucket - (max(bars, 1) - 1) * interval_sec
    rows = []
    price = 100.0
    symbol = str(symbols[0]) if symbols else "demo"
    for i in range(max(bars, 1)):
        ts = start_ts + i * interval_sec
        drift = rng.normal(loc=0.0, scale=0.002)
        open_px = price
        close_px = max(0.1, price * (1 + drift))
        high_px = max(open_px, close_px) + abs(rng.normal(scale=0.05))
        low_px = min(open_px, close_px) - abs(rng.normal(scale=0.05))
        volume = abs(rng.normal(loc=1.0, scale=0.2)) + 0.1
        rows.append(
            {
                "ts": ts,
                "symbol": symbol,
                "open": open_px,
                "high": high_px,
                "low": low_px,
                "close": close_px,
                "volume": volume,
            }
        )
        price = close_px
    return pl.DataFrame(rows)


__all__ = [
    "build_provider_binding",
    "ProviderBinding",
    "WorldDataSelection",
    "apply_data_binding",
    "resolve_world_data_selection",
]
