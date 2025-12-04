from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

import pytest

from .stack import CoreLoopStackHandle


def _http_json(url: str, *, method: str = "GET", data: dict | None = None, timeout: float = 5.0):
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, method=method)
    for key, val in headers.items():
        req.add_header(key, val)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            try:
                js = json.loads(raw) if raw else {}
            except Exception:
                js = {}
            return resp, js
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            js = json.loads(raw) if raw else {}
        except Exception:
            js = {"status": exc.code, "error": raw or str(exc)}
        raise AssertionError({"status": exc.code, "body": js}) from exc
    except Exception as exc:  # noqa: PERF203
        pytest.skip(f"core loop stack not reachable: {exc}")


def _world_id_candidates(world_id: str) -> set[str]:
    return {world_id, world_id.replace("_", "-"), world_id.replace("-", "_")}


def test_core_loop_world_endpoints_available(core_loop_stack: CoreLoopStackHandle, core_loop_world_id: str):
    base = core_loop_stack.worlds_url.rstrip("/")
    wid = urllib.parse.quote(core_loop_world_id)

    resp, js = _http_json(f"{base}/worlds/{wid}")
    assert resp.status == 200
    assert js.get("world", {}).get("id") in _world_id_candidates(core_loop_world_id)

    resp, decision = _http_json(f"{base}/worlds/{wid}/decide")
    assert resp.status == 200
    assert decision.get("world_id") in _world_id_candidates(core_loop_world_id)
    assert any(key in decision for key in ("effective_mode", "ttl", "etag"))

    resp, activation = _http_json(f"{base}/worlds/{wid}/activation")
    assert resp.status == 200
    assert activation.get("world_id") in _world_id_candidates(core_loop_world_id)
    assert "etag" in activation


def test_core_loop_gateway_health(core_loop_stack: CoreLoopStackHandle):
    resp, _ = _http_json(f"{core_loop_stack.gateway_url.rstrip('/')}/health")
    assert resp.status == 200


def test_inproc_stack_sets_service_env(core_loop_stack: CoreLoopStackHandle):
    if core_loop_stack.mode != "inproc":
        pytest.skip("environment wiring applies to the in-process stack only")

    assert os.environ.get("WS_MODE") == "service"
    assert os.environ.get("GATEWAY_URL") == core_loop_stack.gateway_url
    assert os.environ.get("WORLDS_BASE_URL") == core_loop_stack.worlds_url
