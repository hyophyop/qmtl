"""Shared runtime flags for SDK features sourced from configuration."""

from __future__ import annotations

from typing import Any, cast

from . import configuration

# Global flag to disable Ray usage across SDK components.
NO_RAY: bool = False

TEST_MODE: bool = False
FIXED_NOW: int | None = None
HTTP_TIMEOUT_SECONDS: float = 2.0
WS_RECV_TIMEOUT_SECONDS: float = 30.0
WS_MAX_TOTAL_TIME_SECONDS: float | None = None
FAIL_ON_HISTORY_GAP: bool = False
POLL_INTERVAL_SECONDS: float = 10.0
ALPHA_METRICS_CAPABLE: bool = False
REBALANCE_SCHEMA_VERSION: int = 1


def _maybe_int(value: Any) -> int | None:
    if value in {"", None}:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _select(default: float | None, test_override: float | None) -> float | None:
    if TEST_MODE and test_override is not None:
        return test_override
    return default


def _reload_from_config(cfg: Any | None = None) -> None:
    global TEST_MODE, FIXED_NOW, HTTP_TIMEOUT_SECONDS, WS_RECV_TIMEOUT_SECONDS
    global WS_MAX_TOTAL_TIME_SECONDS, FAIL_ON_HISTORY_GAP, POLL_INTERVAL_SECONDS

    unified = cfg or configuration.get_unified_config()
    test_cfg = unified.test
    runtime_cfg = unified.runtime

    TEST_MODE = bool(test_cfg.test_mode)
    FAIL_ON_HISTORY_GAP = bool(test_cfg.fail_on_history_gap)
    FIXED_NOW = _maybe_int(test_cfg.fixed_now)

    HTTP_TIMEOUT_SECONDS = float(
        cast(float, _select(runtime_cfg.http_timeout_seconds, runtime_cfg.http_timeout_seconds_test))
    )
    WS_RECV_TIMEOUT_SECONDS = float(
        cast(
            float,
            _select(runtime_cfg.ws_recv_timeout_seconds, runtime_cfg.ws_recv_timeout_seconds_test),
        )
    )
    WS_MAX_TOTAL_TIME_SECONDS = _select(
        runtime_cfg.ws_max_total_time_seconds, runtime_cfg.ws_max_total_time_seconds_test
    )
    POLL_INTERVAL_SECONDS = float(
        cast(float, _select(runtime_cfg.poll_interval_seconds, runtime_cfg.poll_interval_seconds_test))
    )


def reload() -> None:
    """Reload runtime settings from the unified configuration."""

    cfg = configuration.reload()
    _reload_from_config(cfg)


def set_gateway_capabilities(
    *,
    rebalance_schema_version: int | None = None,
    alpha_metrics_capable: bool | None = None,
) -> None:
    """Update runtime feature flags based on Gateway health."""

    global ALPHA_METRICS_CAPABLE, REBALANCE_SCHEMA_VERSION
    if rebalance_schema_version is not None:
        REBALANCE_SCHEMA_VERSION = max(1, int(rebalance_schema_version))
    if alpha_metrics_capable is not None:
        ALPHA_METRICS_CAPABLE = bool(alpha_metrics_capable)


_reload_from_config()


__all__ = [
    "FAIL_ON_HISTORY_GAP",
    "FIXED_NOW",
    "HTTP_TIMEOUT_SECONDS",
    "NO_RAY",
    "POLL_INTERVAL_SECONDS",
    "TEST_MODE",
    "WS_MAX_TOTAL_TIME_SECONDS",
    "WS_RECV_TIMEOUT_SECONDS",
    "reload",
    "ALPHA_METRICS_CAPABLE",
    "REBALANCE_SCHEMA_VERSION",
    "set_gateway_capabilities",
]
