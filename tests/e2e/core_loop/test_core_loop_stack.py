from __future__ import annotations

import base64
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from qmtl.foundation.common import crc32_of_list
from .stack import CoreLoopStackHandle

pytestmark = pytest.mark.contract


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
        raise AssertionError(f"core loop stack not reachable: {exc}") from exc


def _world_id_candidates(world_id: str) -> set[str]:
    return {world_id, world_id.replace("_", "-"), world_id.replace("-", "_")}


def _submit(strategy: str, *, world: str) -> dict:
    cmd = ["qmtl", "submit", strategy, "--world", world]
    return _submit_raw(cmd)


def _submit_json(strategy: str, *, world: str) -> tuple[dict, dict]:
    cmd = ["qmtl", "submit", strategy, "--world", world, "--output", "json"]
    result = _submit_raw(cmd)
    try:
        payload = json.loads(result["stdout"])
    except Exception as exc:  # noqa: PERF203
        raise AssertionError(f"submit did not emit JSON: rc={result['code']}, stdout={result['stdout']}, stderr={result['stderr']}") from exc
    return payload, result


def _submit_raw(cmd: list[str]) -> dict:
    env = dict(os.environ)
    env.setdefault("QMTL_STRATEGY_ROOT", str(Path(__file__).parent / "worlds"))
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=env,
    )
    if proc.returncode not in (0, 1):  # allow rejected submissions as contract cases
        raise AssertionError(
            f"qmtl submit failed (rc={proc.returncode}):\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    # crude parse: rely on CLI printing SubmitResult(...) repr
    return {"stdout": proc.stdout, "stderr": proc.stderr, "code": proc.returncode}


def _stream_inputs(strategy):
    try:
        from qmtl.runtime.sdk import StreamInput
    except Exception:
        return []
    return [n for n in getattr(strategy, "nodes", []) if isinstance(n, StreamInput)]


def test_submit_default_safe_downgrades_when_missing_as_of(core_loop_world_id: str, monkeypatch: pytest.MonkeyPatch):
    # Ensure deterministic env for the CLI run
    monkeypatch.setenv("QMTL_DEFAULT_WORLD", core_loop_world_id)
    result = _submit(
        "core_loop_demo_strategy:CoreLoopDemoStrategy",
        world=core_loop_world_id,
    )

    # When running without as_of/dataset in backtest, CLI prints a safe mode warning
    assert "Safe mode: execution was downgraded" in result["stderr"]
    assert result["code"] in (0, 1)


def test_submit_reports_downgrade_reason(core_loop_world_id: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QMTL_DEFAULT_WORLD", core_loop_world_id)
    result = _submit(
        "core_loop_demo_strategy:CoreLoopDemoStrategy",
        world=core_loop_world_id,
    )

    # SubmitResult repr should include downgrade flags for contract visibility
    stdout = result["stdout"]
    assert "downgraded" in stdout
    assert "downgrade_reason" in stdout or "missing_as_of" in stdout


def test_submit_json_includes_ws_envelope(core_loop_world_id: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QMTL_DEFAULT_WORLD", core_loop_world_id)
    payload, result = _submit_json(
        "core_loop_demo_strategy:CoreLoopDemoStrategy",
        world=core_loop_world_id,
    )

    # Contract: JSON output keeps WS envelope separate and mirrors downgrade flags.
    assert payload.get("world") == core_loop_world_id
    assert "ws" in payload and isinstance(payload["ws"], dict)
    ws = payload["ws"]

    assert ws.get("world") == core_loop_world_id
    assert ws.get("status") == payload.get("status")
    assert ws.get("downgrade_reason") == payload.get("downgrade_reason")
    assert ws.get("safe_mode") == payload.get("safe_mode")
    assert "precheck" in payload  # even if null, the field should exist
    assert "decision" in payload and "activation" in payload
    assert "decision" in ws and "activation" in ws
    assert result["code"] in (0, 1)


def test_submit_json_includes_allocation(core_loop_world_id: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QMTL_DEFAULT_WORLD", core_loop_world_id)
    payload, result = _submit_json(
        "core_loop_demo_strategy:CoreLoopDemoStrategy",
        world=core_loop_world_id,
    )

    allocation = payload.get("allocation")
    ws_allocation = payload.get("ws", {}).get("allocation")
    assert allocation == ws_allocation
    assert allocation is not None, f"payload={payload}"
    assert allocation.get("world_id") in _world_id_candidates(core_loop_world_id)
    assert "allocation" in allocation
    strategies = allocation.get("strategy_alloc_total")
    if strategies:
        assert isinstance(strategies, dict)
    assert result["code"] in (0, 1)


def test_submit_to_apply_flow(core_loop_world_id: str, core_loop_stack: CoreLoopStackHandle, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QMTL_DEFAULT_WORLD", core_loop_world_id)
    env = dict(os.environ)
    env.setdefault("QMTL_GATEWAY_URL", core_loop_stack.gateway_url)
    payload, _ = _submit_json(
        "core_loop_demo_strategy:CoreLoopDemoStrategy",
        world=core_loop_world_id,
    )
    allocation = payload.get("allocation") or {}
    assert allocation.get("world_id") in _world_id_candidates(core_loop_world_id)

    apply_run = "core-loop-apply"
    proc = subprocess.run(
        ["qmtl", "world", "apply", core_loop_world_id, "--run-id", apply_run],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Apply request sent" in proc.stdout
    assert apply_run in proc.stdout


def test_apply_with_plan_file(core_loop_world_id: str, core_loop_stack: CoreLoopStackHandle, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QMTL_DEFAULT_WORLD", core_loop_world_id)
    env = dict(os.environ)
    env.setdefault("QMTL_GATEWAY_URL", core_loop_stack.gateway_url)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({"plan": {"activate": ["s-demo"]}}))

    proc = subprocess.run(
        [
            "qmtl",
            "world",
            "apply",
            core_loop_world_id,
            "--plan-file",
            str(plan_file),
            "--run-id",
            "plan-run",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Apply request sent" in proc.stdout
    assert "plan-run" in proc.stdout


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


def test_gateway_metrics_capture_nodeid_mismatch(core_loop_stack: CoreLoopStackHandle):
    if not core_loop_stack.metrics_url:
        pytest.skip("metrics endpoint not exposed")

    node = {
        "node_type": "TagQueryNode",
        "code_hash": "code",
        "config_hash": "cfg",
        "schema_hash": "schema",
        "schema_compat_id": "schema-major",
        "params": {"tags": ["demo"], "match_mode": "any"},
        "tags": ["demo"],
        "interval": 60,
        "dependencies": [],
        "node_id": "blake3:incorrect",
    }
    dag = {"schema_version": "v1", "nodes": [node]}
    payload = {
        "dag_json": base64.b64encode(json.dumps(dag).encode()).decode(),
        "meta": None,
        "node_ids_crc32": crc32_of_list([node["node_id"]]),
    }

    req = urllib.request.Request(
        f"{core_loop_stack.gateway_url.rstrip('/')}/strategies",
        data=json.dumps(payload).encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "submission should fail with node_id mismatch"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        body = exc.read().decode("utf-8", errors="ignore")
        assert "E_NODE_ID_MISMATCH" in body

    metrics_resp = urllib.request.urlopen(core_loop_stack.metrics_url, timeout=5)
    metrics_text = metrics_resp.read().decode()
    assert "nodeid_mismatch_total" in metrics_text
    assert 'node_type="TagQueryNode"' in metrics_text
    assert "tagquery_nodeid_mismatch_total" in metrics_text


def test_inproc_stack_sets_service_env(core_loop_stack: CoreLoopStackHandle):
    if core_loop_stack.mode != "inproc":
        pytest.skip("environment wiring applies to the in-process stack only")

    assert os.environ.get("WS_MODE") == "service"
    assert os.environ.get("GATEWAY_URL") == core_loop_stack.gateway_url
    assert os.environ.get("WORLDS_BASE_URL") == core_loop_stack.worlds_url


@pytest.mark.asyncio
async def test_world_data_preset_autowires_seamless_provider(core_loop_world_id: str):
    from qmtl.runtime.sdk import Runner
    from tests.e2e.core_loop.worlds.core_loop_demo_strategy import CoreLoopDemoStrategy

    result = Runner.submit(
        CoreLoopDemoStrategy,
        world=core_loop_world_id,
        auto_validate=False,
    )
    strategy = result.strategy
    assert strategy is not None
    streams = _stream_inputs(strategy)
    assert streams, "strategy should expose at least one StreamInput"

    stream = streams[0]
    provider = stream.history_provider
    assert provider is not None

    interval_val = int(stream.interval) if isinstance(stream.interval, (int, float)) else int(str(stream.interval).rstrip("s"))
    coverage = await provider.coverage(node_id=stream.node_id, interval=interval_val)
    assert coverage, "auto-wired provider should seed demo coverage"
    assert stream.dataset_fingerprint

    cfg = getattr(provider, "_seamless_config", None)
    if cfg is not None:
        assert getattr(cfg, "sla_preset", None) == "baseline"
