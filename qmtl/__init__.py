"""Public API surface for the QMTL package."""

from __future__ import annotations

import asyncio
import importlib
import sys
from typing import Any, Mapping

# Ensure ASGI transports from httpx are properly closed when garbage collected.
try:  # pragma: no cover - best effort cleanup helper
    import httpx

    class _ClosingASGITransport(httpx.ASGITransport):
        """Ensure transports are closed and remain compatible with httpx>=0.28."""

        def __init__(self, *args: Any, lifespan: Any = None, **kwargs: Any) -> None:
            if lifespan is not None:  # pragma: no cover - simple arg shim
                kwargs.pop("lifespan", None)
            super().__init__(*args, **kwargs)

        def __del__(self) -> None:
            try:
                closer = self.aclose()
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(closer)
                else:
                    loop.create_task(closer)
            except Exception:
                pass

    setattr(httpx, "ASGITransport", _ClosingASGITransport)
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
    "io",
]

_MODULE_MAP: Mapping[str, str] = {
    "foundation": "qmtl.foundation",
    "interfaces": "qmtl.interfaces",
    "runtime": "qmtl.runtime",
    "services": "qmtl.services",
    "examples": "qmtl.examples",
    "io": "qmtl.runtime.io",
}

_ATTR_MAP: Mapping[str, tuple[str, str | None]] = {
    # Pipeline
    "Pipeline": ("qmtl.runtime.pipeline.pipeline", "Pipeline"),
    # Strategy SDK
    "Strategy": ("qmtl.runtime.sdk.strategy", "Strategy"),
    "Runner": ("qmtl.runtime.sdk.runner", "Runner"),
    "Node": ("qmtl.runtime.sdk.node", "Node"),
    "ProcessingNode": ("qmtl.runtime.sdk.node", "ProcessingNode"),
    "SourceNode": ("qmtl.runtime.sdk.node", "SourceNode"),
    "StreamInput": ("qmtl.runtime.sdk.node", "StreamInput"),
    "TagQueryNode": ("qmtl.runtime.sdk.node", "TagQueryNode"),
    "CacheView": ("qmtl.runtime.sdk.cache_view", "CacheView"),
    "MatchMode": ("qmtl.runtime.sdk.node", "MatchMode"),
    "EventRecorderService": ("qmtl.runtime.sdk.event_service", "EventRecorderService"),
    "TradeExecutionService": (
        "qmtl.runtime.sdk.trade_execution_service",
        "TradeExecutionService",
    ),
    "metrics": ("qmtl.runtime.sdk.metrics", None),
    # IO helpers
    "QuestDBLoader": ("qmtl.runtime.io.historyprovider", "QuestDBLoader"),
    "QuestDBRecorder": ("qmtl.runtime.io.eventrecorder", "QuestDBRecorder"),
    "BinanceFetcher": ("qmtl.runtime.io.binance_fetcher", "BinanceFetcher"),
    "DataFetcher": ("qmtl.runtime.sdk.data_io", "DataFetcher"),
    "HistoryProvider": ("qmtl.runtime.sdk.data_io", "HistoryProvider"),
    "EventRecorder": ("qmtl.runtime.sdk.data_io", "EventRecorder"),
    # Helpers
    "parse_interval": ("qmtl.runtime.sdk.util", "parse_interval"),
    "parse_period": ("qmtl.runtime.sdk.util", "parse_period"),
    "validate_tag": ("qmtl.runtime.sdk.util", "validate_tag"),
    "validate_name": ("qmtl.runtime.sdk.util", "validate_name"),
    # Exceptions
    "QMTLValidationError": ("qmtl.runtime.sdk.exceptions", "QMTLValidationError"),
    "NodeValidationError": ("qmtl.runtime.sdk.exceptions", "NodeValidationError"),
    "InvalidParameterError": ("qmtl.runtime.sdk.exceptions", "InvalidParameterError"),
    "InvalidTagError": ("qmtl.runtime.sdk.exceptions", "InvalidTagError"),
    "InvalidIntervalError": ("qmtl.runtime.sdk.exceptions", "InvalidIntervalError"),
    "InvalidPeriodError": ("qmtl.runtime.sdk.exceptions", "InvalidPeriodError"),
    "InvalidNameError": ("qmtl.runtime.sdk.exceptions", "InvalidNameError"),
}


def __getattr__(name: str) -> Any:
    if name == "io":
        module = importlib.import_module(_MODULE_MAP[name])
        sys.modules[__name__ + ".io"] = module
        globals()[name] = module
        return module

    if name in _MODULE_MAP:
        module = importlib.import_module(_MODULE_MAP[name])
        globals()[name] = module
        return module

    target = _ATTR_MAP.get(name)
    if target is None:
        raise AttributeError(name)
    module_path, attr = target
    module = importlib.import_module(module_path)
    value = module if attr is None else getattr(module, attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__))
