from __future__ import annotations

import io
import json

import pytest

from qmtl.foundation.schema import SchemaRegistryClient


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._buf = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self) -> bytes:
        return self._buf.getvalue()

    def __enter__(self):  # pragma: no cover - exercised indirectly
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover - passthrough
        return False


@pytest.mark.asyncio
async def test_remote_registry_register_latest_get_by_id_and_from_env(monkeypatch):
    # Minimal in-memory remote service state
    state: dict[str, list[tuple[int, str]]] = {}
    next_id = {"val": 100}

    def fake_urlopen(req, timeout=5):  # type: ignore[no-untyped-def]
        url: str = getattr(req, "full_url", req)  # Request or str
        method: str = getattr(req, "method", "GET")
        body = getattr(req, "data", None)
        path = url.split("://", 1)[-1].split("/", 1)[-1]  # strip scheme/host
        if isinstance(body, (bytes, bytearray)):
            payload = json.loads(body.decode("utf-8"))
        else:
            payload = None
        # Routes
        if method == "POST" and path.startswith("subjects/") and path.endswith("/versions"):
            subject = path.split("/", 2)[1]
            sch = payload["schema"] if isinstance(payload, dict) else "{}"
            sid = next_id["val"]
            next_id["val"] += 1
            state.setdefault(subject, []).append((sid, sch))
            return _Resp({"id": sid})
        if method == "GET" and path.startswith("subjects/") and path.endswith("/versions/latest"):
            subject = path.split("/", 2)[1]
            versions = state.get(subject) or []
            if not versions:
                return _Resp({"id": 0, "schema": "{}", "version": 0})
            sid, sch = versions[-1]
            return _Resp({"id": sid, "schema": sch, "version": len(versions)})
        if method == "GET" and path.startswith("schemas/ids/"):
            sid = int(path.split("/")[-1])
            for subj, versions in state.items():
                for idv, sch in versions:
                    if idv == sid:
                        return _Resp({"schema": sch})
            return _Resp({"schema": "{}"})
        raise AssertionError(f"unexpected request: {method} {path}")

    # Patch env and urlopen
    monkeypatch.setenv("QMTL_SCHEMA_REGISTRY_URL", "http://mock")
    import urllib.request as _req

    monkeypatch.setattr(_req, "urlopen", fake_urlopen)

    # Create client from env and exercise endpoints
    client = SchemaRegistryClient.from_env()
    # register -> returns id; latest -> reflects last
    s1 = client.register("prices", json.dumps({"a": 1}))
    assert s1.id >= 100 and s1.version >= 1
    latest = client.latest("prices")
    assert latest and latest.id == s1.id and json.loads(latest.schema)["a"] == 1
    # second register should compute version 2
    s2 = client.register("prices", json.dumps({"a": 1, "b": 2}))
    assert s2.version >= s1.version
    # get by id
    g = client.get_by_id(s1.id)
    assert g and json.loads(g.schema)["a"] == 1
