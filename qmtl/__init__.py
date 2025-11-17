"""Public API surface for the QMTL package."""

from __future__ import annotations

import importlib
import sys
from typing import Any, cast

foundation = importlib.import_module("qmtl.foundation")
interfaces = importlib.import_module("qmtl.interfaces")
runtime = importlib.import_module("qmtl.runtime")
services = importlib.import_module("qmtl.services")
examples = importlib.import_module("qmtl.examples")

io = importlib.import_module("qmtl.runtime.io")
QuestDBLoader = cast(Any, io).QuestDBLoader
QuestDBRecorder = cast(Any, io).QuestDBRecorder
BinanceFetcher = cast(Any, io).BinanceFetcher
DataFetcher = cast(Any, io).DataFetcher
HistoryProvider = cast(Any, io).HistoryProvider
EventRecorder = cast(Any, io).EventRecorder

Pipeline = cast(Any, importlib.import_module("qmtl.runtime.pipeline")).Pipeline

# Create io alias
sys.modules[__name__ + '.io'] = io

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
