from .pipeline import Pipeline

# Thin re-exports of core SDK entrypoints for convenience
# Keep internal layout under qmtl.sdk; expose commonly used classes at top level.
from .sdk import (
    Strategy,
    Runner,
    Node,
    ProcessingNode,
    SourceNode,
    StreamInput,
    TagQueryNode,
    CacheView,
    MatchMode,
    EventRecorderService,
    TradeExecutionService,
    metrics,
    # helpers
    parse_interval,
    parse_period,
    validate_tag,
    validate_name,
    # exceptions
    QMTLValidationError,
    NodeValidationError,
    InvalidParameterError,
    InvalidTagError,
    InvalidIntervalError,
    InvalidPeriodError,
    InvalidNameError,
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
]
