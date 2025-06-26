from __future__ import annotations
from dataclasses import dataclass
from typing import Any

import yaml


@dataclass
class GatewayConfig:
    """Configuration for Gateway service."""

    redis_dsn: str = "redis://localhost:6379"
    database_backend: str = "postgres"
    database_dsn: str = "postgresql://localhost/qmtl"
    offline: bool = False


def load_gateway_config(path: str) -> GatewayConfig:
    """Load configuration from YAML or JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise TypeError("Gateway config must be a mapping")
    return GatewayConfig(**data)
