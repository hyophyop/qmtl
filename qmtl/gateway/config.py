from __future__ import annotations
from dataclasses import dataclass, field
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
    # WorldService proxy configuration
    worldservice_url: str = "http://localhost:8421"
    worldservice_timeout: float = 0.3
    worldservice_retries: int = 2
    worldservice_enabled: bool = True
    # ControlBus (optional) configuration
    controlbus_brokers: list[str] = field(default_factory=list)
    controlbus_dsn: Optional[str] = None
    controlbus_topics: list[str] = field(default_factory=list)
    controlbus_group: str = "gateway"
