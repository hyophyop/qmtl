from .pipeline import Pipeline

# Thin re-exports of core SDK entrypoints for convenience
# Keep internal layout under qmtl.sdk; expose commonly used classes at top level.
from .sdk import (
    Strategy,
    Runner,
    Node,
    StreamInput,
    TagQueryNode,
    EventRecorderService,
)

# Ensure ASGI transports from httpx are properly closed when garbage collected.
try:  # pragma: no cover - best effort cleanup helper
    import httpx

    class _ClosingASGITransport(httpx.ASGITransport):
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
    "StreamInput",
    "TagQueryNode",
    "EventRecorderService",
]
