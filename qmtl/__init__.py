"""Public API surface for the QMTL package."""

from __future__ import annotations

import sys

from . import foundation, interfaces, runtime, services, examples
from .runtime import io
from .runtime.io import (
    BinanceFetcher,
    DataFetcher,
    EventRecorder,
    HistoryProvider,
    QuestDBLoader,
    QuestDBRecorder,
)
from .runtime.pipeline import Pipeline

# Create io alias
sys.modules[__name__ + ".io"] = io

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
                self.close()  # type: ignore[attr-defined]
            except Exception:
                pass

    httpx.ASGITransport = _ClosingASGITransport  # type: ignore[misc]
except Exception:  # pragma: no cover - optional
    pass

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
    # io
    "QuestDBLoader",
    "QuestDBRecorder",
    "BinanceFetcher",
    "DataFetcher",
    "HistoryProvider",
    "EventRecorder",
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
    "examples",
]
