from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet
import logging
import os
from typing import Any, Dict, Mapping

import yaml

from qmtl.services.gateway.config import GatewayConfig
from qmtl.services.dagmanager.config import DagManagerConfig
from qmtl.services.worldservice.config import (
    WorldServiceServerConfig,
    load_worldservice_server_config,
)

logger = logging.getLogger(__name__)


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
    test: TestConfig = field(default_factory=TestConfig)
    present_sections: FrozenSet[str] = field(default_factory=frozenset)


def find_config_file(cwd: Path | None = None) -> str | None:
    """Return configuration path preferring ``QMTL_CONFIG_FILE`` when set."""

    base = Path.cwd() if cwd is None else cwd

    env_override = os.getenv("QMTL_CONFIG_FILE")
    if env_override:
        candidate = Path(env_override)
        if not candidate.is_absolute():
            candidate = base / candidate
        if candidate.is_file():
            return str(candidate)
        logger.warning("QMTL_CONFIG_FILE=%s does not point to a readable file", env_override)

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


def load_config(path: str) -> UnifiedConfig:
    """Parse YAML/JSON and populate :class:`UnifiedConfig`."""
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

    gw_data = data.get("gateway", {})
    dm_data = data.get("dagmanager", {})
    world_data = data.get("worldservice", {})
    seamless_data = data.get("seamless", {})
    connectors_data = data.get("connectors", {})
    telemetry_data = data.get("telemetry", {})
    cache_data = data.get("cache", {})
    test_data = data.get("test", {})
    present_sections: FrozenSet[str] = frozenset(
        section
        for section in CONFIG_SECTION_NAMES
        if section in data and isinstance(data.get(section), dict)
    )

    for section_name, section_data in (
        ("gateway", gw_data),
        ("dagmanager", dm_data),
        ("worldservice", world_data),
        ("seamless", seamless_data),
        ("connectors", connectors_data),
        ("telemetry", telemetry_data),
        ("cache", cache_data),
        ("test", test_data),
    ):
        if section_data is None:
            section_data = {}
        if not isinstance(section_data, dict):
            raise TypeError(f"{section_name} section must be a mapping")
        if section_name == "gateway":
            gw_data = section_data
        elif section_name == "dagmanager":
            dm_data = section_data
        elif section_name == "worldservice":
            world_data = section_data
        elif section_name == "seamless":
            seamless_data = section_data
        elif section_name == "connectors":
            connectors_data = section_data
        elif section_name == "telemetry":
            telemetry_data = section_data
        elif section_name == "cache":
            cache_data = section_data
        elif section_name == "test":
            test_data = section_data

    # Apply transitional aliases for connection-string keys to *_dsn
    # Canonical keys take precedence if both are provided.
    def _apply_aliases(section: dict, aliases: dict[str, str], *, logger_prefix: str) -> dict:
        out = dict(section)
        for alias, canonical in aliases.items():
            if canonical in out:
                continue
            if alias in out:
                logger.warning("%s: key '%s' is deprecated; use '%s' instead", logger_prefix, alias, canonical)
                out[canonical] = out.pop(alias)
        return out

    gw_aliases = {
        "redis_url": "redis_dsn",
        "redis_uri": "redis_dsn",
        "database_url": "database_dsn",
        "database_uri": "database_dsn",
        "controlbus_url": "controlbus_dsn",
        "controlbus_uri": "controlbus_dsn",
    }
    dm_aliases = {
        "neo4j_url": "neo4j_dsn",
        "neo4j_uri": "neo4j_dsn",
        "kafka_url": "kafka_dsn",
        "kafka_uri": "kafka_dsn",
        "controlbus_url": "controlbus_dsn",
        "controlbus_uri": "controlbus_dsn",
    }

    gw_data = _apply_aliases(gw_data, gw_aliases, logger_prefix="gateway")
    dm_data = _apply_aliases(dm_data, dm_aliases, logger_prefix="dagmanager")

    # Backfill canonical WorldService settings from legacy Gateway keys to keep
    # `worldservice` exports populated for configurations that have not migrated
    # yet. Only fill values that are missing from the dedicated section so that
    # explicit ``worldservice`` entries continue to take precedence.
    world_data = dict(world_data)
    server_data: Mapping[str, Any] | None = None
    inline_server: dict[str, Any] = {}
    for inline_key in ("dsn", "redis", "bind", "auth"):
        if inline_key in world_data:
            inline_server[inline_key] = world_data.pop(inline_key)

    if "server" in world_data:
        raw_server = world_data.pop("server")
        if raw_server is None:
            raw_server = {}
        if not isinstance(raw_server, Mapping):
            raise TypeError("worldservice.server must be a mapping")
        merged_server = dict(raw_server)
        if inline_server:
            merged_server.update(inline_server)
        server_data = merged_server
    elif inline_server:
        server_data = inline_server
    legacy_worldservice_keys = {
        "worldservice_url": "url",
        "worldservice_timeout": "timeout",
        "worldservice_retries": "retries",
        "enable_worldservice_proxy": "enable_proxy",
        "enforce_live_guard": "enforce_live_guard",
    }
    for legacy_key, canonical_key in legacy_worldservice_keys.items():
        if canonical_key in world_data:
            continue
        if legacy_key in gw_data:
            world_data[canonical_key] = gw_data[legacy_key]

    # Deprecated breaker keys are no longer filtered; invalid keys should be surfaced

    gateway_cfg = GatewayConfig.from_mapping(gw_data)
    dagmanager_cfg = DagManagerConfig(**dm_data)
    server_cfg: WorldServiceServerConfig | None = None
    if server_data is not None:
        server_cfg = load_worldservice_server_config(server_data)

    worldservice_cfg = WorldServiceConfig(**world_data, server=server_cfg)
    seamless_cfg = SeamlessConfig(**seamless_data)
    connectors_cfg = ConnectorsConfig(**connectors_data)
    telemetry_cfg = TelemetryConfig(**telemetry_data)
    cache_cfg = CacheConfig(**cache_data)
    test_cfg = TestConfig(**test_data)

    # Canonical WorldService settings live in the dedicated section; mirror them into
    # the legacy Gateway fields when provided to maintain compatibility.
    if world_data:
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

    return UnifiedConfig(
        worldservice=worldservice_cfg,
        gateway=gateway_cfg,
        dagmanager=dagmanager_cfg,
        seamless=seamless_cfg,
        connectors=connectors_cfg,
        telemetry=telemetry_cfg,
        cache=cache_cfg,
        test=test_cfg,
        present_sections=present_sections,
    )
