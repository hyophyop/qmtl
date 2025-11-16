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
    compat_rebalance_v2: bool = False
    alpha_metrics_required: bool = False


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
    bind_cfg = _parse_bind_config(raw)
    auth_cfg = _parse_auth_config(raw)
    compat_rebalance_v2 = bool(raw.get("compat_rebalance_v2", False))
    alpha_metrics_required = bool(raw.get("alpha_metrics_required", False))

    return WorldServiceServerConfig(
        dsn=dsn,
        redis=redis_dsn,
        bind=bind_cfg,
        auth=auth_cfg,
        compat_rebalance_v2=compat_rebalance_v2,
        alpha_metrics_required=alpha_metrics_required,
    )


def _parse_bind_config(raw: Mapping[str, Any]) -> WorldServiceBindConfig:
    if "bind" not in raw or raw["bind"] is None:
        return WorldServiceBindConfig()
    bind_data = _ensure_mapping("bind", raw["bind"])
    bind_kwargs: dict[str, Any] = {}
    if "host" in bind_data:
        bind_kwargs["host"] = bind_data["host"]
    if "port" in bind_data:
        bind_kwargs["port"] = bind_data["port"]
    return WorldServiceBindConfig(**bind_kwargs)


def _parse_auth_config(raw: Mapping[str, Any]) -> WorldServiceAuthConfig:
    if "auth" not in raw or raw["auth"] is None:
        return WorldServiceAuthConfig()
    auth_data = _ensure_mapping("auth", raw["auth"])
    auth_kwargs: dict[str, Any] = {}
    if "header" in auth_data:
        auth_kwargs["header"] = auth_data["header"]
    if "tokens" in auth_data:
        tokens = auth_data["tokens"]
        auth_kwargs["tokens"] = _normalize_auth_tokens(tokens)
    return WorldServiceAuthConfig(**auth_kwargs)


def _normalize_auth_tokens(tokens: Any) -> list[str]:
    if tokens is None:
        return []
    if isinstance(tokens, list):
        if not all(isinstance(token, str) for token in tokens):
            raise TypeError("WorldService auth tokens must be strings")
        return list(tokens)
    raise TypeError("WorldService auth tokens must be provided as a list")


__all__ = [
    "WorldServiceAuthConfig",
    "WorldServiceBindConfig",
    "WorldServiceServerConfig",
    "load_worldservice_server_config",
]
