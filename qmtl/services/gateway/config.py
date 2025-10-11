from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
import logging
import secrets

from .event_descriptor import EventDescriptorConfig


@dataclass
class GatewayConfig:
    """Configuration for Gateway service."""

    host: str = "0.0.0.0"
    port: int = 8000
    redis_dsn: Optional[str] = None
    database_backend: str = "sqlite"
    database_dsn: str = "./qmtl.db"
    insert_sentinel: bool = True
    controlbus_brokers: list[str] = field(default_factory=list)
    controlbus_dsn: Optional[str] = None
    controlbus_topics: list[str] = field(default_factory=list)
    controlbus_group: str = "gateway"
    commitlog_bootstrap: Optional[str] = None
    commitlog_topic: Optional[str] = "gateway.ingest"
    commitlog_group: str = "gateway-commit"
    commitlog_transactional_id: str = "gateway-commit-writer"
    worldservice_url: Optional[str] = None
    worldservice_timeout: float = 0.3
    worldservice_retries: int = 2
    enable_worldservice_proxy: bool = True
    enforce_live_guard: bool = True
    events: "GatewayEventsConfig" = field(default_factory=lambda: GatewayEventsConfig())
    websocket: "GatewayWebSocketConfig" = field(
        default_factory=lambda: GatewayWebSocketConfig()
    )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "GatewayConfig":
        """Construct :class:`GatewayConfig` from a raw mapping."""

        base = dict(data)
        events_data = base.pop("events", {}) or {}
        websocket_data = base.pop("websocket", {}) or {}
        cfg = cls(**base)
        if isinstance(events_data, GatewayEventsConfig):
            cfg.events = events_data
        elif isinstance(events_data, dict):
            cfg.events = GatewayEventsConfig(**events_data)
        else:
            raise TypeError("gateway.events must be a mapping")
        if isinstance(websocket_data, GatewayWebSocketConfig):
            cfg.websocket = websocket_data
        elif isinstance(websocket_data, dict):
            cfg.websocket = GatewayWebSocketConfig(**websocket_data)
        else:
            raise TypeError("gateway.websocket must be a mapping")
        return cfg


@dataclass
class GatewayEventsConfig:
    """Event descriptor configuration exposed via YAML."""

    secret: str | None = None
    keys: dict[str, str] = field(default_factory=dict)
    active_kid: str = "default"
    ttl: int = 300
    stream_url: str = "wss://gateway/ws/evt"
    fallback_url: str = "wss://gateway/ws"

    def build_descriptor(
        self, *, logger: logging.Logger | None = None
    ) -> EventDescriptorConfig:
        """Return :class:`EventDescriptorConfig` derived from YAML settings."""

        keys = dict(self.keys)
        if self.secret:
            keys.setdefault(self.active_kid, self.secret)
        if not keys:
            secret = secrets.token_hex(32)
            if logger is not None:
                logger.warning(
                    "Gateway events.secret not configured; using a generated secret"
                )
            keys[self.active_kid] = secret
        return EventDescriptorConfig(
            keys=keys,
            active_kid=self.active_kid,
            ttl=self.ttl,
            stream_url=self.stream_url,
            fallback_url=self.fallback_url,
        )


@dataclass
class GatewayWebSocketConfig:
    """WebSocket hub configuration."""

    rate_limit_per_sec: int | None = None
