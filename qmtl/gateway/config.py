from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import logging
import yaml


@dataclass
class GatewayConfig:
    """Configuration for Gateway service."""

    host: str = "0.0.0.0"
    port: int = 8000
    redis_dsn: Optional[str] = None
    database_backend: str = "sqlite"
    database_dsn: str = "./qmtl.db"


def load_gateway_config(path: str) -> GatewayConfig:
    """Load configuration from YAML or JSON file."""
    logger = logging.getLogger(__name__)
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
        raise TypeError("Gateway config must be a mapping")
    cfg = GatewayConfig(**data)
    return cfg
