from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import logging
import yaml

from .gateway.config import GatewayConfig
from .dagmanager.config import DagManagerConfig

logger = logging.getLogger(__name__)


@dataclass
class UnifiedConfig:
    """Configuration aggregating gateway and DAG manager settings."""

    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    dagmanager: DagManagerConfig = field(default_factory=DagManagerConfig)


def find_config_file(cwd: Path | None = None) -> str | None:
    """Return path to ``qmtl.yml``/``qmtl.yaml`` in ``cwd`` if present."""

    base = Path.cwd() if cwd is None else cwd
    for name in ("qmtl.yml", "qmtl.yaml"):
        candidate = base / name
        if candidate.is_file():
            return str(candidate)
    return None


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

    # Breaker timeouts were removed; services now reset breakers manually
    # based on explicit success signals.
    for key in ("dagclient_breaker_timeout", "kafka_breaker_timeout", "neo4j_breaker_timeout"):
        gw_data.pop(key, None)
        dm_data.pop(key, None)

    gateway_cfg = GatewayConfig(**gw_data)
    dagmanager_cfg = DagManagerConfig(**dm_data)
    return UnifiedConfig(gateway=gateway_cfg, dagmanager=dagmanager_cfg)
