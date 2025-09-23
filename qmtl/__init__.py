"""Public API surface for the QMTL package."""

from __future__ import annotations

from . import foundation, interfaces, runtime, services
from ._compat import deprecated_module
from .runtime.pipeline import Pipeline
from .runtime.sdk import (
    CacheView,
    EventRecorderService,
    InvalidIntervalError,
    InvalidNameError,
    InvalidParameterError,
    InvalidPeriodError,
    InvalidTagError,
    MatchMode,
    Node,
    NodeValidationError,
    ProcessingNode,
    Runner,
    SourceNode,
    Strategy,
    StreamInput,
    TagQueryNode,
    TradeExecutionService,
    metrics,
    parse_interval,
    parse_period,
    validate_name,
    validate_tag,
    QMTLValidationError,
)

# Ensure ASGI transports from httpx are properly closed when garbage collected.
try:  # pragma: no cover - best effort cleanup helper
    import httpx

    class _ClosingASGITransport(httpx.ASGITransport):
        """Ensure transports are closed and remain compatible with httpx>=0.28."""

        def __init__(self, *args, lifespan=None, **kwargs):  # type: ignore[no-untyped-def]
            # ``lifespan`` was removed in httpx 0.28 but is still passed by some
            # callers. Accept and discard it for backwards compatibility.
            if lifespan is not None:  # pragma: no cover - simple arg shim
                kwargs.pop("lifespan", None)
            super().__init__(*args, **kwargs)

        def __del__(self) -> None:
            try:
                self.close()
            except Exception:
                pass

    httpx.ASGITransport = _ClosingASGITransport
except Exception:  # pragma: no cover - optional
    pass

_DEPRECATED_ALIASES = {
    "common": "qmtl.foundation.common",
    "schema": "qmtl.foundation.schema",
    "kafka": "qmtl.foundation.kafka",
    "proto": "qmtl.foundation.proto",
    "config": "qmtl.foundation.config",
    "spec": "qmtl.foundation.spec",
    "gateway": "qmtl.services.gateway",
    "dagmanager": "qmtl.services.dagmanager",
    "worldservice": "qmtl.services.worldservice",
    "sdk": "qmtl.runtime.sdk",
    "pipeline": "qmtl.runtime.pipeline",
    "nodesets": "qmtl.runtime.nodesets",
    "transforms": "qmtl.runtime.transforms",
    "indicators": "qmtl.runtime.indicators",
    "generators": "qmtl.runtime.generators",
    "brokerage": "qmtl.runtime.brokerage",
    "reference_models": "qmtl.runtime.reference_models",
    "io": "qmtl.runtime.io",
    "cli": "qmtl.interfaces.cli",
    "tools": "qmtl.interfaces.tools",
    "scripts": "qmtl.interfaces.scripts",
    "scaffold": "qmtl.interfaces.scaffold",
}


def __getattr__(name: str):  # type: ignore[override]
    if name in _DEPRECATED_ALIASES:
        module = deprecated_module(f"{__name__}.{name}", _DEPRECATED_ALIASES[name])
        globals()[name] = module
        return module
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "Pipeline",
    "Strategy",
    "Runner",
    "Node",
    "ProcessingNode",
    "SourceNode",
    "StreamInput",
    "TagQueryNode",
    "CacheView",
    "MatchMode",
    "EventRecorderService",
    "TradeExecutionService",
    "metrics",
    # helpers
    "parse_interval",
    "parse_period",
    "validate_tag",
    "validate_name",
    # exceptions
    "QMTLValidationError",
    "NodeValidationError",
    "InvalidParameterError",
    "InvalidTagError",
    "InvalidIntervalError",
    "InvalidPeriodError",
    "InvalidNameError",
    # primary namespace entrypoints
    "foundation",
    "interfaces",
    "runtime",
    "services",
]
