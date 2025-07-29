from .pipeline import Pipeline

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

__all__ = ["Pipeline"]
