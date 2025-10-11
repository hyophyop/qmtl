"""Runtime configuration helpers for SDK components."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
import logging

from qmtl.foundation.config import (
    ConnectorsConfig,
    SeamlessConfig,
    UnifiedConfig,
    find_config_file,
    load_config,
)

logger = logging.getLogger(__name__)

_CONFIG_OVERRIDE: UnifiedConfig | None = None
_CONFIG_CACHE: UnifiedConfig | None = None
_CONFIG_CACHE_LOADED: bool = False
_CONFIG_SOURCE_PATH: str | None = None


def _load_from_path(path: str | Path) -> UnifiedConfig:
    return load_config(str(path))


def set_runtime_config_override(config: UnifiedConfig | None) -> None:
    """Set a process-wide override for the runtime configuration."""

    global _CONFIG_OVERRIDE, _CONFIG_SOURCE_PATH
    _CONFIG_OVERRIDE = config
    _CONFIG_SOURCE_PATH = None


def reset_runtime_config_cache() -> None:
    """Clear the cached runtime configuration."""

    global _CONFIG_CACHE, _CONFIG_CACHE_LOADED, _CONFIG_SOURCE_PATH
    _CONFIG_CACHE = None
    _CONFIG_CACHE_LOADED = False
    _CONFIG_SOURCE_PATH = None


@contextmanager
def runtime_config_override(config: UnifiedConfig | None) -> Iterator[None]:
    """Temporarily override the runtime configuration returned by helpers."""

    global _CONFIG_SOURCE_PATH
    previous_override = _CONFIG_OVERRIDE
    previous_source = _CONFIG_SOURCE_PATH
    set_runtime_config_override(config)
    try:
        yield
    finally:
        set_runtime_config_override(previous_override)
        _CONFIG_SOURCE_PATH = previous_source


def get_runtime_config(path: str | Path | None = None) -> UnifiedConfig | None:
    """Return the active runtime configuration or ``None`` when unavailable."""

    if path is not None:
        return _load_from_path(path)

    override = _CONFIG_OVERRIDE
    if override is not None:
        return override

    global _CONFIG_CACHE_LOADED, _CONFIG_CACHE, _CONFIG_SOURCE_PATH
    if _CONFIG_CACHE_LOADED:
        return _CONFIG_CACHE

    cfg_path = find_config_file()
    if not cfg_path:
        logger.debug("No qmtl config file discovered; using defaults")
        _CONFIG_CACHE_LOADED = True
        _CONFIG_CACHE = None
        _CONFIG_SOURCE_PATH = None
        return None

    try:
        _CONFIG_CACHE = _load_from_path(cfg_path)
        _CONFIG_SOURCE_PATH = cfg_path
    finally:
        _CONFIG_CACHE_LOADED = True
    return _CONFIG_CACHE


def get_runtime_config_path() -> str | None:
    """Return the path used for the cached runtime configuration."""

    if _CONFIG_OVERRIDE is not None:
        return None
    if not _CONFIG_CACHE_LOADED:
        get_runtime_config()
    return _CONFIG_SOURCE_PATH


def get_seamless_config(path: str | Path | None = None) -> SeamlessConfig:
    """Return seamless configuration from runtime config or defaults."""

    unified = get_runtime_config(path)
    if unified is not None:
        return unified.seamless
    return SeamlessConfig()


def get_connectors_config(path: str | Path | None = None) -> ConnectorsConfig:
    """Return connectors configuration from runtime config or defaults."""

    unified = get_runtime_config(path)
    if unified is not None:
        return unified.connectors
    return ConnectorsConfig()


__all__ = [
    "get_runtime_config",
    "get_runtime_config_path",
    "get_seamless_config",
    "get_connectors_config",
    "runtime_config_override",
    "reset_runtime_config_cache",
    "set_runtime_config_override",
]

# ---------------------------------------------------------------------------
# Backwards-compatibility shims for legacy accessor names used within SDK
# ---------------------------------------------------------------------------

def get_unified_config(*, reload: bool = False) -> UnifiedConfig:
    if reload:
        reset_runtime_config_cache()
    cfg = get_runtime_config()
    return cfg or UnifiedConfig()


def reload() -> UnifiedConfig:
    reset_runtime_config_cache()
    return get_unified_config()
