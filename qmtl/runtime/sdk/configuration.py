"""Helpers for loading the unified SDK configuration."""

from __future__ import annotations
import logging
from typing import Optional

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import-time cycle guard
    from qmtl.foundation.config import (
        CacheConfig,
        ConnectorsConfig,
        RuntimeConfig,
        TestConfig,
        UnifiedConfig,
    )

logger = logging.getLogger(__name__)

_CONFIG: Optional["UnifiedConfig"] = None
_CONFIG_PATH: Optional[str] = None


def _load_from_path(path: Optional[str]) -> "UnifiedConfig":
    from qmtl.foundation.config import UnifiedConfig, load_config

    if not path:
        return UnifiedConfig()
    try:
        return load_config(path)
    except FileNotFoundError:
        logger.warning("Configuration file %s was not found; using defaults", path)
    except Exception as exc:  # pragma: no cover - defensive catch
        logger.warning("Failed to load configuration file %s: %s", path, exc)
    return UnifiedConfig()


def get_unified_config(*, reload: bool = False) -> "UnifiedConfig":
    """Return the cached :class:`~qmtl.foundation.config.UnifiedConfig`."""

    global _CONFIG, _CONFIG_PATH
    if reload:
        _CONFIG = None
        _CONFIG_PATH = None

    from qmtl.foundation.config import find_config_file

    path = find_config_file()
    if _CONFIG is None or path != _CONFIG_PATH:
        _CONFIG = _load_from_path(path)
        _CONFIG_PATH = path
    return _CONFIG


def reload() -> "UnifiedConfig":
    """Force a reload of the configuration file."""

    return get_unified_config(reload=True)


def cache_config() -> "CacheConfig":
    return get_unified_config().cache


def runtime_config() -> "RuntimeConfig":
    return get_unified_config().runtime


def connectors_config() -> "ConnectorsConfig":
    return get_unified_config().connectors


def test_config() -> "TestConfig":
    return get_unified_config().test


__all__ = [
    "cache_config",
    "connectors_config",
    "get_unified_config",
    "reload",
    "runtime_config",
    "test_config",
]
