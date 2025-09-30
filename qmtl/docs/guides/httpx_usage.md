# HTTPX Usage

QMTL targets httpx 0.28.x and uses its updated ASGI testing APIs. This page documents the required patterns to keep tests and examples consistent and future‑proof.

## Version policy

- Dependency pin: `httpx>=0.28,<0.29`
- Rationale: httpx 0.28 introduced context-managed `ASGITransport` and related changes; pinning to 0.28.x avoids accidental breakage from future minor releases.

## ASGI testing pattern (async)

Use the context-manager form of `ASGITransport` and nest an `AsyncClient`:

```python
import httpx

async with httpx.ASGITransport(app=app) as transport:
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/status")
        assert resp.status_code == 200
```

Do not instantiate `ASGITransport(app)` without a context manager and do not manually call `aclose()`; the context takes care of cleanup.

## Mocking upstream services

Prefer `httpx.MockTransport` in tests over ad‑hoc servers:

```python
async def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})

transport = httpx.MockTransport(handler)
client = httpx.AsyncClient(transport=transport)
```

## WebSockets

When testing WebSocket endpoints exposed by FastAPI/Starlette, continue using `fastapi.testclient.TestClient` for sync tests, and the `ASGITransport` pattern above for async HTTP interactions around them.

## Migration notes (pre‑0.28 → 0.28)

- Replace `transport = httpx.ASGITransport(app)` + manual `aclose()` with the context-manager form shown above.
- Ensure `base_url` is set on the client when targeting ASGI apps.

