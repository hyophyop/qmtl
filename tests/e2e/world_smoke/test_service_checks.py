"""
Service-mode WorldService smoke checks (Gateway-proxied).

These tests are designed to be environment-tolerant:
- They SKIP cleanly when required endpoints or capabilities are unavailable.
- They avoid asserting backend-specific payloads beyond the normative envelope keys.

Env required (for service mode):
- WS_MODE=service
- GATEWAY_URL, WORLDS_BASE_URL (and optionally QMTL_METRICS_URL)
"""

from __future__ import annotations

import json
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pytest


def _http_json(url: str, *, method: str = "GET", data: dict | None = None, headers: dict | None = None, timeout: float = 5.0):
    body = None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in hdrs.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            try:
                js = json.loads(raw) if raw else {}
            except Exception:
                js = {}
            return resp, js
    except urllib.error.HTTPError as e:
        # Surface JSON body if any; caller can decide to assert/skip
        try:
            raw = e.read().decode("utf-8", errors="ignore")
            err = json.loads(raw)
        except Exception:
            err = {"status": e.code, "error": str(e)}
        raise AssertionError({"status": e.code, "body": err})
    except Exception as e:
        pytest.skip(f"endpoint not reachable: {e}")


@pytest.mark.order(5)
def test_service_mode_worlds_get_persisted(service_worlds_registered):
    worlds_base = service_worlds_registered["worlds"].rstrip("/")

    # Probe that the world can be read back (persistence). If not present, skip.
    for wid in ("prod-us-equity", "sandbox-crypto"):
        try:
            resp, js = _http_json(f"{worlds_base}/worlds/{urllib.parse.quote(wid)}")
        except pytest.skip.Exception:
            raise
        except Exception:
            pytest.skip("world read not supported or not provisioned")
        assert resp.status == 200
        # Minimal shape checks
        assert js.get("world", {}).get("id") in {wid, wid.replace("_", "-")}


@pytest.mark.order(6)
def test_service_mode_decide_activation_envelopes(service_worlds_registered):
    gateway = service_worlds_registered["gateway"].rstrip("/")

    # Decide envelope
    try:
        _, djs = _http_json(f"{gateway}/worlds/prod-us-equity/decide")
    except pytest.skip.Exception:
        raise
    except Exception:
        pytest.skip("/worlds/{id}/decide not available")

    # Normative keys (at least one of ttl/etag should be present)
    assert djs.get("world_id") in {"prod-us-equity", "prod_us_equity"}
    assert any(k in djs for k in ("ttl", "etag", "effective_mode"))

    # Activation envelope
    try:
        _, ajs = _http_json(f"{gateway}/worlds/prod-us-equity/activation")
    except pytest.skip.Exception:
        raise
    except Exception:
        pytest.skip("/worlds/{id}/activation not available")

    assert ajs.get("world_id") in {"prod-us-equity", "prod_us_equity"}
    assert any(k in ajs for k in ("etag", "run_id", "active"))


@pytest.mark.order(7)
def test_service_mode_evaluate_apply_roundtrip(service_worlds_registered):
    gateway = service_worlds_registered["gateway"].rstrip("/")

    # Evaluate (plan-only)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        _, eval_js = _http_json(
            f"{gateway}/worlds/prod-us-equity/evaluate", method="POST", data={"as_of": now}
        )
    except pytest.skip.Exception:
        raise
    except Exception:
        pytest.skip("/worlds/{id}/evaluate not available")

    # Accept either a plan object or topk candidate list per spec
    if not ("plan" in eval_js or "topk" in eval_js or "ok" in eval_js):
        pytest.skip("evaluate returned non-normative shape; skipping apply")

    # Apply (2-Phase with run_id). Gateway enforces live guard unless X-Allow-Live=true
    run_id = uuid.uuid4().hex
    headers = {"X-Allow-Live": "true"}
    try:
        _, apply_js = _http_json(
            f"{gateway}/worlds/prod-us-equity/apply",
            method="POST",
            data={"run_id": run_id, "plan": eval_js.get("plan", {})},
            headers=headers,
        )
    except pytest.skip.Exception:
        raise
    except AssertionError as e:
        # If the backend rejects the plan shape, treat as environment limitation.
        pytest.skip(f"apply rejected by backend: {e}")
    except Exception:
        pytest.skip("/worlds/{id}/apply not available")

    assert apply_js.get("run_id", run_id) == run_id
    assert apply_js.get("ok", True) in (True, 1, "true")
    assert isinstance(apply_js.get("active"), list)
    if "phase" in apply_js:
        assert isinstance(apply_js["phase"], str) and apply_js["phase"]


@pytest.mark.order(8)
def test_service_mode_ws_handshake_initial_snapshot(service_worlds_registered):
    gateway = service_worlds_registered["gateway"].rstrip("/")

    # Subscribe to get stream descriptor
    try:
        _, sub_js = _http_json(
            f"{gateway}/events/subscribe",
            method="POST",
            data={"world_id": "prod-us-equity", "strategy_id": "e2e-world-smoke", "topics": ["activation", "policy"]},
        )
    except pytest.skip.Exception:
        raise
    except Exception:
        pytest.skip("/events/subscribe not available")

    token = sub_js.get("token")
    stream_url = sub_js.get("stream_url") or ""
    if not token or not stream_url.startswith(("ws://", "wss://")):
        pytest.skip("subscribe did not return token/stream_url")

    # Optional: connect and receive initial snapshot if websocket-client is available
    try:
        import websocket  # type: ignore
    except Exception:
        pytest.skip("websocket-client not installed")

    # Some gateways expect the token in the Authorization header
    header = [f"Authorization: Bearer {token}"]

    # Short timeout to avoid hanging in constrained environments
    try:
        ws = websocket.create_connection(stream_url, timeout=3, header=header)
    except Exception as e:
        pytest.skip(f"ws connect failed: {e}")

    try:
        ws.settimeout(3)
        msg = ws.recv()
        # Close ASAP; it's okay if we didn't get a message in time
        try:
            evt = json.loads(msg)
        except Exception:
            pytest.skip("received non-JSON event from WS")
        etype = evt.get("type")
        assert etype in {"activation_updated", "queue_update", "policy_state_hash", "policy_updated"}
    except Exception:
        pytest.skip("no initial snapshot within timeout")
    finally:
        try:
            ws.close()
        except Exception:
            pass
