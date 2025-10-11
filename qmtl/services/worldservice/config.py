"""Configuration helpers for the standalone WorldService API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class WorldServiceBindConfig:
    """Network binding configuration for the WorldService HTTP server."""

    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class WorldServiceAuthConfig:
    """Authentication configuration for protecting the WorldService API."""

    header: str = "Authorization"
    tokens: list[str] = field(default_factory=list)


@dataclass
class WorldServiceServerConfig:
    """Runtime configuration for the WorldService application server."""

    dsn: str
    redis: str | None = None
    bind: WorldServiceBindConfig = field(default_factory=WorldServiceBindConfig)
    auth: WorldServiceAuthConfig = field(default_factory=WorldServiceAuthConfig)


def _ensure_mapping(name: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"WorldService {name} configuration must be a mapping")
    return value


def load_worldservice_server_config(data: Mapping[str, Any]) -> WorldServiceServerConfig:
    """Coerce raw mapping data into :class:`WorldServiceServerConfig`.

    Parameters
    ----------
    data:
        Mapping extracted from the unified configuration file.

    Returns
    -------
    WorldServiceServerConfig
        Parsed configuration object with defaults applied.

    Raises
    ------
    ValueError
        If the required ``dsn`` field is missing or falsy.
    TypeError
        If nested ``bind`` or ``auth`` structures are not mappings.
    """

    raw = dict(data)
    dsn = raw.get("dsn")
    if not dsn:
        raise ValueError("WorldService configuration requires 'dsn'")

    redis_dsn = raw.get("redis")

    bind_cfg = WorldServiceBindConfig()
    if "bind" in raw and raw["bind"] is not None:
        bind_data = _ensure_mapping("bind", raw["bind"])
        bind_kwargs: dict[str, Any] = {}
        if "host" in bind_data:
            bind_kwargs["host"] = bind_data["host"]
        if "port" in bind_data:
            bind_kwargs["port"] = bind_data["port"]
        bind_cfg = WorldServiceBindConfig(**bind_kwargs)

    auth_cfg = WorldServiceAuthConfig()
    if "auth" in raw and raw["auth"] is not None:
        auth_data = _ensure_mapping("auth", raw["auth"])
        auth_kwargs: dict[str, Any] = {}
        if "header" in auth_data:
            auth_kwargs["header"] = auth_data["header"]
        if "tokens" in auth_data:
            tokens = auth_data["tokens"]
            if tokens is None:
                auth_kwargs["tokens"] = []
            elif isinstance(tokens, list):
                if not all(isinstance(token, str) for token in tokens):
                    raise TypeError("WorldService auth tokens must be strings")
                auth_kwargs["tokens"] = list(tokens)
            else:
                raise TypeError("WorldService auth tokens must be provided as a list")
        auth_cfg = WorldServiceAuthConfig(**auth_kwargs)

    return WorldServiceServerConfig(dsn=dsn, redis=redis_dsn, bind=bind_cfg, auth=auth_cfg)


__all__ = [
    "WorldServiceAuthConfig",
    "WorldServiceBindConfig",
    "WorldServiceServerConfig",
    "load_worldservice_server_config",
]

