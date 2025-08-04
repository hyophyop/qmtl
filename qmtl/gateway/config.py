from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import yaml


@dataclass
class GatewayConfig:
    """Configuration for Gateway service."""

    host: str = "0.0.0.0"
    port: int = 8000
    redis_dsn: Optional[str] = None
    database_backend: str = "sqlite"
    database_dsn: str = "./qmtl.db"
    dagclient_breaker_threshold: int = 3
    dagclient_breaker_timeout: float = 60.0


def load_gateway_config(path: str) -> GatewayConfig:
    """Load configuration from YAML or JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise TypeError("Gateway config must be a mapping")
    cfg = GatewayConfig(**data)
    return cfg
