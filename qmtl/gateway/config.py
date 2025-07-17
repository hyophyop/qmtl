from __future__ import annotations
from dataclasses import dataclass
from typing import Any

import yaml


@dataclass
class GatewayConfig:
    """Configuration for Gateway service."""

    host: str = "0.0.0.0"
    port: int = 8000
    redis_dsn: str = "redis://localhost:6379"
    database_backend: str = "sqlite"
    database_dsn: str = "./qmtl.db"
    queue_backend: str = "memory"
    dagclient_breaker_threshold: int = 3
    dagclient_breaker_timeout: float = 60.0


def load_gateway_config(path: str) -> GatewayConfig:
    """Load configuration from YAML or JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise TypeError("Gateway config must be a mapping")
    cfg = GatewayConfig(**data)
    if cfg.queue_backend not in {"memory", "redis"}:
        raise ValueError("queue_backend must be 'memory' or 'redis'")
    return cfg
