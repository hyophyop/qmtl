from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import logging
import os
import yaml

from qmtl.services.gateway.config import GatewayConfig
from qmtl.services.dagmanager.config import DagManagerConfig

logger = logging.getLogger(__name__)


@dataclass
class UnifiedConfig:
    """Configuration aggregating gateway and DAG Manager settings."""

    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    dagmanager: DagManagerConfig = field(default_factory=DagManagerConfig)


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

    if not isinstance(gw_data, dict):
        raise TypeError("gateway section must be a mapping")
    if not isinstance(dm_data, dict):
        raise TypeError("dagmanager section must be a mapping")

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

    # Deprecated breaker keys are no longer filtered; invalid keys should be surfaced

    gateway_cfg = GatewayConfig(**gw_data)
    dagmanager_cfg = DagManagerConfig(**dm_data)
    return UnifiedConfig(gateway=gateway_cfg, dagmanager=dagmanager_cfg)
