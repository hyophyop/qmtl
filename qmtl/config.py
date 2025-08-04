from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import yaml

from .gateway.config import GatewayConfig
from .dagmanager.config import DagManagerConfig


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
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        raise TypeError("Unified config must be a mapping")

    gw_data = data.get("gateway", {})
    dm_data = data.get("dagmanager", {})

    if not isinstance(gw_data, dict):
        raise TypeError("gateway section must be a mapping")
    if not isinstance(dm_data, dict):
        raise TypeError("dagmanager section must be a mapping")

    gateway_cfg = GatewayConfig(**gw_data)
    dagmanager_cfg = DagManagerConfig(**dm_data)
    return UnifiedConfig(gateway=gateway_cfg, dagmanager=dagmanager_cfg)
