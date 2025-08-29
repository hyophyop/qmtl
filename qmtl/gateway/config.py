from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class GatewayConfig:
    """Configuration for Gateway service."""

    host: str = "0.0.0.0"
    port: int = 8000
    redis_dsn: Optional[str] = None
    database_backend: str = "sqlite"
    database_dsn: str = "./qmtl.db"
    insert_sentinel: bool = True
    worldservice_url: str = "http://localhost:8421"
    worldservice_timeout: float = 0.3
    worldservice_retries: int = 2
    worldservice_enabled: bool = True
