from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Mapping

import yaml  # type: ignore[import-untyped]

from qmtl.services.gateway.config import GatewayConfig
from qmtl.services.dagmanager.config import DagManagerConfig
from qmtl.services.worldservice.config import (
    WorldServiceServerConfig,
    load_worldservice_server_config,
)

logger = logging.getLogger(__name__)


_GATEWAY_ALIASES: dict[str, str] = {
    "redis_url": "redis_dsn",
    "redis_uri": "redis_dsn",
    "database_url": "database_dsn",
    "database_uri": "database_dsn",
    "controlbus_url": "controlbus_dsn",
    "controlbus_uri": "controlbus_dsn",
}

_DAGMANAGER_ALIASES: dict[str, str] = {
    "neo4j_url": "neo4j_dsn",
    "neo4j_uri": "neo4j_dsn",
    "kafka_url": "kafka_dsn",
    "kafka_uri": "kafka_dsn",
    "controlbus_url": "controlbus_dsn",
    "controlbus_uri": "controlbus_dsn",
}

_WORLD_INLINE_SERVER_KEYS: tuple[str, ...] = (
    "dsn",
    "redis",
    "bind",
    "auth",
    "compat_rebalance_v2",
    "alpha_metrics_required",
)

_LEGACY_WORLDSERVICE_KEYS: dict[str, str] = {
    "worldservice_url": "url",
    "worldservice_timeout": "timeout",
    "worldservice_retries": "retries",
    "enable_worldservice_proxy": "enable_proxy",
    "enforce_live_guard": "enforce_live_guard",
}


@dataclass
class WorldServiceConfig:
    """WorldService proxy configuration shared across services."""

    url: str | None = None
    timeout: float = 0.3
    retries: int = 2
    enable_proxy: bool = True
    enforce_live_guard: bool = True
    cache_ttl_seconds: int | None = None
    cache_max_entries: int | None = None
    server: WorldServiceServerConfig | None = None


@dataclass
class SeamlessConfig:
    """Configuration for Seamless coordinator, artifacts, and governance."""

    coordinator_url: str | None = field(
        default=None, metadata={"env": "QMTL_SEAMLESS_COORDINATOR_URL"}
    )
    artifacts_enabled: bool = field(
        default=False, metadata={"env": "QMTL_SEAMLESS_ARTIFACTS"}
    )
    artifact_dir: str = field(
        default="~/.qmtl_seamless_artifacts",
        metadata={"env": "QMTL_SEAMLESS_ARTIFACT_DIR"},
    )
    fingerprint_mode: str = field(
        default="canonical", metadata={"env": "QMTL_SEAMLESS_FP_MODE"}
    )
    publish_fingerprint: bool = field(
        default=True, metadata={"env": "QMTL_SEAMLESS_PUBLISH_FP"}
    )
    preview_fingerprint: bool = field(
        default=False, metadata={"env": "QMTL_SEAMLESS_PREVIEW_FP"}
    )
    early_fingerprint: bool = field(
        default=False, metadata={"env": "QMTL_SEAMLESS_EARLY_FP"}
    )
    sla_preset: str = field(
        default="baseline", metadata={"env": "QMTL_SEAMLESS_SLA_PRESET"}
    )
    conformance_preset: str = field(
        default="strict-blocking",
        metadata={"env": "QMTL_SEAMLESS_CONFORMANCE_PRESET"},
    )
    presets_file: str | None = None


@dataclass
class ConnectorsConfig:
    """Connector- and worker-level integration settings."""

    ccxt_rate_limiter_redis: str | None = field(
        default=None, metadata={"env": "QMTL_CCXT_RATE_LIMITER_REDIS"}
    )
    schema_registry_url: str | None = field(
        default=None, metadata={"env": "QMTL_SCHEMA_REGISTRY_URL"}
    )
    worker_id: str | None = field(
        default=None, metadata={"env": "QMTL_WORKER_ID"}
    )
    seamless_worker_id: str | None = field(
        default=None, metadata={"env": "QMTL_SEAMLESS_WORKER"}
    )
    strategy_id: str | None = field(
        default=None, metadata={"env": "QMTL_STRATEGY_ID"}
    )
    execution_domain: str | None = field(
        default=None, metadata={"env": "QMTL_EXECUTION_DOMAIN"}
    )
    broker_url: str | None = field(
        default=None, metadata={"env": "QMTL_BROKER_URL"}
    )
    trade_max_retries: int = field(
        default=3, metadata={"env": "QMTL_TRADE_MAX_RETRIES"}
    )
    trade_backoff: float = field(
        default=0.1, metadata={"env": "QMTL_TRADE_BACKOFF"}
    )
    ws_url: str | None = field(
        default=None, metadata={"env": "QMTL_WS_URL"}
    )


@dataclass
class RuntimeConfig:
    """SDK runtime tuning knobs (timeouts, polling)."""

    http_timeout_seconds: float = 2.0
    http_timeout_seconds_test: float = 1.5
    ws_recv_timeout_seconds: float = 30.0
    ws_recv_timeout_seconds_test: float = 5.0
    ws_max_total_time_seconds: float | None = None
    ws_max_total_time_seconds_test: float | None = 5.0
    poll_interval_seconds: float = 10.0
    poll_interval_seconds_test: float = 2.0


@dataclass
class TelemetryConfig:
    """Telemetry sinks and tracing exporters."""

    otel_exporter_endpoint: str | None = field(
        default=None, metadata={"env": "QMTL_OTEL_EXPORTER_ENDPOINT"}
    )
    enable_fastapi_otel: bool = field(
        default=False, metadata={"env": "QMTL_ENABLE_FASTAPI_OTEL"}
    )
    prometheus_url: str | None = field(
        default=None, metadata={"env": "QMTL_PROMETHEUS_URL"}
    )


@dataclass
class CacheConfig:
    """Local cache and artifact persistence controls."""

    arrow_cache_enabled: bool = field(
        default=False, metadata={"env": "QMTL_ARROW_CACHE"}
    )
    cache_evict_interval: int = field(
        default=60, metadata={"env": "QMTL_CACHE_EVICT_INTERVAL"}
    )
    feature_artifacts_enabled: bool = field(
        default=False, metadata={"env": "QMTL_FEATURE_ARTIFACTS"}
    )
    feature_artifact_dir: str = field(
        default=".qmtl_feature_artifacts",
        metadata={"env": "QMTL_FEATURE_ARTIFACT_DIR"},
    )
    feature_artifact_versions: int | None = field(
        default=None, metadata={"env": "QMTL_FEATURE_ARTIFACT_VERSIONS"}
    )
    feature_artifact_write_domains: list[str] = field(
        default_factory=list,
        metadata={"env": "QMTL_FEATURE_ARTIFACT_WRITE_DOMAINS"},
    )
    tagquery_cache_path: str = field(
        default=".qmtl_tagmap.json", metadata={"env": "QMTL_TAGQUERY_CACHE"}
    )
    snapshot_dir: str = field(
        default=".qmtl_snapshots", metadata={"env": "QMTL_SNAPSHOT_DIR"}
    )
    snapshot_url: str | None = field(
        default=None, metadata={"env": "QMTL_SNAPSHOT_URL"}
    )
    snapshot_strict_runtime: bool = field(
        default=False, metadata={"env": "QMTL_SNAPSHOT_STRICT_RUNTIME"}
    )
    snapshot_format: str = field(
        default="json", metadata={"env": "QMTL_SNAPSHOT_FORMAT"}
    )


@dataclass
class TestConfig:
    """Runtime toggles for integration tests and deterministic runs."""

    test_mode: bool = field(default=False, metadata={"env": "QMTL_TEST_MODE"})
    fail_on_history_gap: bool = field(
        default=False, metadata={"env": "QMTL_FAIL_ON_HISTORY_GAP"}
    )
    fixed_now: str | None = field(
        default=None, metadata={"env": "QMTL_FIXED_NOW"}
    )
    history_start: str | None = field(
        default=None, metadata={"env": "QMTL_HISTORY_START"}
    )
    history_end: str | None = field(
        default=None, metadata={"env": "QMTL_HISTORY_END"}
    )


CONFIG_SECTION_NAMES: tuple[str, ...] = (
    "worldservice",
    "gateway",
    "dagmanager",
    "seamless",
    "connectors",
    "telemetry",
    "cache",
    "runtime",
    "test",
)


ENV_EXPORT_PREFIXES: Dict[str, str] = {
    "gateway": "QMTL__GATEWAY__",
    "dagmanager": "QMTL__DAGMANAGER__",
}


ENV_EXPORT_OVERRIDES: Dict[str, Dict[str, str | None]] = {
    "worldservice": {
        "url": "QMTL__GATEWAY__WORLDSERVICE_URL",
        "timeout": "QMTL__GATEWAY__WORLDSERVICE_TIMEOUT",
        "retries": "QMTL__GATEWAY__WORLDSERVICE_RETRIES",
        "enable_proxy": "QMTL__GATEWAY__ENABLE_WORLDSERVICE_PROXY",
        "enforce_live_guard": "QMTL__GATEWAY__ENFORCE_LIVE_GUARD",
        "cache_ttl_seconds": "QMTL__GATEWAY__WORLDSERVICE_CACHE_TTL",
        "cache_max_entries": "QMTL__GATEWAY__WORLDSERVICE_CACHE_MAX",
    },
    "seamless": {
        "coordinator_url": "QMTL_SEAMLESS_COORDINATOR_URL",
        "artifacts_enabled": "QMTL_SEAMLESS_ARTIFACTS",
        "artifact_dir": "QMTL_SEAMLESS_ARTIFACT_DIR",
        "fingerprint_mode": "QMTL_SEAMLESS_FP_MODE",
        "publish_fingerprint": "QMTL_SEAMLESS_PUBLISH_FP",
        "preview_fingerprint": "QMTL_SEAMLESS_PREVIEW_FP",
        "early_fingerprint": "QMTL_SEAMLESS_EARLY_FP",
        "sla_preset": "QMTL_SEAMLESS_SLA_PRESET",
        "conformance_preset": "QMTL_SEAMLESS_CONFORMANCE_PRESET",
    },
    "connectors": {
        "ccxt_rate_limiter_redis": "QMTL_CCXT_RATE_LIMITER_REDIS",
        "schema_registry_url": "QMTL_SCHEMA_REGISTRY_URL",
        "worker_id": "QMTL_WORKER_ID",
        "seamless_worker_id": "QMTL_SEAMLESS_WORKER",
        "strategy_id": "QMTL_STRATEGY_ID",
        "execution_domain": "QMTL_EXECUTION_DOMAIN",
        "broker_url": "QMTL_BROKER_URL",
        "trade_max_retries": "QMTL_TRADE_MAX_RETRIES",
        "trade_backoff": "QMTL_TRADE_BACKOFF",
        "ws_url": "QMTL_WS_URL",
    },
    "telemetry": {
        "otel_exporter_endpoint": "QMTL_OTEL_EXPORTER_ENDPOINT",
        "enable_fastapi_otel": "QMTL_ENABLE_FASTAPI_OTEL",
        "prometheus_url": "QMTL_PROMETHEUS_URL",
    },
    "cache": {
        "arrow_cache_enabled": "QMTL_ARROW_CACHE",
        "cache_evict_interval": "QMTL_CACHE_EVICT_INTERVAL",
        "feature_artifacts_enabled": "QMTL_FEATURE_ARTIFACTS",
        "feature_artifact_dir": "QMTL_FEATURE_ARTIFACT_DIR",
        "feature_artifact_versions": "QMTL_FEATURE_ARTIFACT_VERSIONS",
        "feature_artifact_write_domains": "QMTL_FEATURE_ARTIFACT_WRITE_DOMAINS",
        "tagquery_cache_path": "QMTL_TAGQUERY_CACHE",
        "snapshot_dir": "QMTL_SNAPSHOT_DIR",
        "snapshot_url": "QMTL_SNAPSHOT_URL",
        "snapshot_strict_runtime": "QMTL_SNAPSHOT_STRICT_RUNTIME",
        "snapshot_format": "QMTL_SNAPSHOT_FORMAT",
    },
    "runtime": {
        "http_timeout_seconds": "QMTL_HTTP_TIMEOUT",
        "http_timeout_seconds_test": "QMTL_HTTP_TIMEOUT_TEST",
        "ws_recv_timeout_seconds": "QMTL_WS_RECV_TIMEOUT",
        "ws_recv_timeout_seconds_test": "QMTL_WS_RECV_TIMEOUT_TEST",
        "ws_max_total_time_seconds": "QMTL_WS_MAX_TOTAL_TIME",
        "ws_max_total_time_seconds_test": "QMTL_WS_MAX_TOTAL_TIME_TEST",
        "poll_interval_seconds": "QMTL_POLL_INTERVAL",
        "poll_interval_seconds_test": "QMTL_POLL_INTERVAL_TEST",
    },
    "test": {
        "test_mode": "QMTL_TEST_MODE",
        "fail_on_history_gap": "QMTL_FAIL_ON_HISTORY_GAP",
        "fixed_now": "QMTL_FIXED_NOW",
        "history_start": "QMTL_HISTORY_START",
        "history_end": "QMTL_HISTORY_END",
    },
}


ENV_EXPORT_IGNORED_FIELDS: Dict[str, set[str]] = {
    "gateway": {
        "worldservice_url",
        "worldservice_timeout",
        "worldservice_retries",
        "enable_worldservice_proxy",
        "enforce_live_guard",
    }
}


@dataclass
class UnifiedConfig:
    """Configuration aggregating service, runtime, and tooling settings."""

    worldservice: WorldServiceConfig = field(default_factory=WorldServiceConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    dagmanager: DagManagerConfig = field(default_factory=DagManagerConfig)
    seamless: SeamlessConfig = field(default_factory=SeamlessConfig)
    connectors: ConnectorsConfig = field(default_factory=ConnectorsConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    test: TestConfig = field(default_factory=TestConfig)
    present_sections: FrozenSet[str] = field(default_factory=frozenset)


def find_config_file(cwd: Path | None = None) -> str | None:
    """Return the first discoverable configuration file in ``cwd``."""

    base = Path.cwd() if cwd is None else cwd

    for name in ("qmtl.yml", "qmtl.yaml"):
        candidate = base / name
        if candidate.is_file():
            return str(candidate)
    return None


def has_config_section(path: str, section: str) -> bool:
    """Return ``True`` if ``section`` exists in the configuration file."""

    try:
        with open(path, "r", encoding="utf-8") as fh:
            try:
                data = yaml.safe_load(fh) or {}
            except yaml.YAMLError:
                return False
    except (FileNotFoundError, OSError):
        return False

    if not isinstance(data, dict):
        return False
    return section in data


def _read_config_mapping(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            try:
                data = yaml.safe_load(fh) or {}
            except yaml.YAMLError as exc:
                logger.error("Failed to parse configuration file %s: %s", path, exc)
                raise ValueError(f"Failed to parse configuration file {path}") from exc
    except (FileNotFoundError, OSError) as exc:
        logger.error("Unable to open configuration file %s: %s", path, exc)
        raise

    if not isinstance(data, dict):
        raise TypeError("Unified config must be a mapping")
    return data


def _extract_sections(data: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], FrozenSet[str]]:
    present_sections: FrozenSet[str] = frozenset(
        section
        for section in CONFIG_SECTION_NAMES
        if section in data and isinstance(data.get(section), dict)
    )

    sections: dict[str, dict[str, Any]] = {}
    for section_name in CONFIG_SECTION_NAMES:
        raw_section = data.get(section_name, {})
        if raw_section is None:
            raw_section = {}
        if not isinstance(raw_section, dict):
            raise TypeError(f"{section_name} section must be a mapping")
        sections[section_name] = dict(raw_section)
    return sections, present_sections


def _apply_aliases(section: Mapping[str, Any], aliases: Mapping[str, str], *, logger_prefix: str) -> dict[str, Any]:
    normalized = dict(section)
    for alias, canonical in aliases.items():
        if canonical in normalized:
            continue
        if alias in normalized:
            logger.warning(
                "%s: key '%s' is deprecated; use '%s' instead",
                logger_prefix,
                alias,
                canonical,
            )
            normalized[canonical] = normalized.pop(alias)
    return normalized


def _collect_inline_worldservice_server(world_data: dict[str, Any]) -> dict[str, Any]:
    inline_server: dict[str, Any] = {}
    for inline_key in _WORLD_INLINE_SERVER_KEYS:
        if inline_key in world_data:
            inline_server[inline_key] = world_data.pop(inline_key)
    return inline_server


def _merge_worldservice_server(
    normalized_world: dict[str, Any], inline_server: dict[str, Any]
) -> Mapping[str, Any] | None:
    if "server" not in normalized_world:
        return inline_server or None

    raw_server = normalized_world.pop("server")
    if raw_server is None:
        raw_server = {}
    if not isinstance(raw_server, Mapping):
        raise TypeError("worldservice.server must be a mapping")

    merged_server = dict(raw_server)
    if inline_server:
        merged_server.update(inline_server)
    return merged_server


def _backfill_legacy_worldservice(
    normalized_world: dict[str, Any], gateway_data: Mapping[str, Any]
) -> None:
    for legacy_key, canonical_key in _LEGACY_WORLDSERVICE_KEYS.items():
        if canonical_key in normalized_world:
            continue
        if legacy_key in gateway_data:
            normalized_world[canonical_key] = gateway_data[legacy_key]


def _prepare_worldservice(
    world_data: Mapping[str, Any], gateway_data: Mapping[str, Any]
) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    normalized_world = dict(world_data)
    inline_server = _collect_inline_worldservice_server(normalized_world)
    server_data = _merge_worldservice_server(normalized_world, inline_server)
    _backfill_legacy_worldservice(normalized_world, gateway_data)
    return normalized_world, server_data


def _mirror_worldservice_to_gateway(
    world_data: Mapping[str, Any],
    worldservice_cfg: WorldServiceConfig,
    gateway_cfg: GatewayConfig,
) -> None:
    if not world_data:
        return

    if "url" in world_data:
        gateway_cfg.worldservice_url = worldservice_cfg.url
    if "timeout" in world_data:
        gateway_cfg.worldservice_timeout = worldservice_cfg.timeout
    if "retries" in world_data:
        gateway_cfg.worldservice_retries = worldservice_cfg.retries
    if "enable_proxy" in world_data:
        gateway_cfg.enable_worldservice_proxy = worldservice_cfg.enable_proxy
    if "enforce_live_guard" in world_data:
        gateway_cfg.enforce_live_guard = worldservice_cfg.enforce_live_guard


def load_config(path: str) -> UnifiedConfig:
    """Parse YAML/JSON and populate :class:`UnifiedConfig`."""
    data = _read_config_mapping(path)
    sections, present_sections = _extract_sections(data)

    gateway_data = _apply_aliases(sections["gateway"], _GATEWAY_ALIASES, logger_prefix="gateway")
    dagmanager_data = _apply_aliases(
        sections["dagmanager"], _DAGMANAGER_ALIASES, logger_prefix="dagmanager"
    )
    world_data, server_data = _prepare_worldservice(sections["worldservice"], gateway_data)

    seamless_data = sections["seamless"]
    connectors_data = sections["connectors"]
    telemetry_data = sections["telemetry"]
    cache_data = sections["cache"]
    runtime_data = sections["runtime"]
    test_data = sections["test"]

    gateway_cfg = GatewayConfig.from_mapping(gateway_data)
    dagmanager_cfg = DagManagerConfig(**dagmanager_data)
    server_cfg = (
        load_worldservice_server_config(server_data) if server_data is not None else None
    )
    worldservice_cfg = WorldServiceConfig(**world_data, server=server_cfg)
    seamless_cfg = SeamlessConfig(**seamless_data)
    connectors_cfg = ConnectorsConfig(**connectors_data)
    telemetry_cfg = TelemetryConfig(**telemetry_data)
    cache_cfg = CacheConfig(**cache_data)
    runtime_cfg = RuntimeConfig(**runtime_data)
    test_cfg = TestConfig(**test_data)

    _mirror_worldservice_to_gateway(world_data, worldservice_cfg, gateway_cfg)

    return UnifiedConfig(
        worldservice=worldservice_cfg,
        gateway=gateway_cfg,
        dagmanager=dagmanager_cfg,
        seamless=seamless_cfg,
        connectors=connectors_cfg,
        telemetry=telemetry_cfg,
        cache=cache_cfg,
        runtime=runtime_cfg,
        test=test_cfg,
        present_sections=present_sections,
    )
