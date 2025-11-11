import httpx
import pytest

from qmtl.services.gateway import metrics as gw_metrics
from qmtl.services.gateway.shared_account_policy import SharedAccountPolicyConfig
from tests.qmtl.services.gateway.helpers import StubCommitLogWriter


def _plan_response(per_world, *, global_deltas=None):
    return {
        "per_world": per_world,
        "global_deltas": global_deltas or [],
    }


def _default_payload():
    return {
        "total_equity": 100000.0,
        "world_alloc_before": {"w1": 1.0},
        "world_alloc_after": {"w1": 1.0},
        "positions": [
            {
                "world_id": "w1",
                "strategy_id": "s1",
                "symbol": "BTCUSDT",
                "qty": 1.0,
                "mark": 30000.0,
                "venue": "binance",
            }
        ],
    }


@pytest.mark.asyncio
async def test_rebalancing_submit_requires_live_guard(gateway_app_factory):
    writer = StubCommitLogWriter()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            body = _plan_response(
                {
                    "w1": {
                        "scale_world": 1.0,
                        "scale_by_strategy": {},
                        "deltas": [
                            {"symbol": "BTCUSDT", "delta_qty": -0.5, "venue": "binance"}
                        ],
                    }
                }
            )
            return httpx.Response(200, json=body)
        if request.method == "GET" and request.url.path == "/worlds/w1":
            return httpx.Response(200, json={"world": {"id": "w1", "mode": "simulate"}})
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(handler, commit_log_writer=writer) as ctx:
        resp = await ctx.client.post(
            "/rebalancing/execute?submit=true",
            json=_default_payload(),
        )

    assert resp.status_code == 403
    assert writer.published == []


@pytest.mark.asyncio
async def test_rebalancing_submit_records_metrics_and_audit(
    gateway_app_factory, reset_gateway_metrics
) -> None:
    writer = StubCommitLogWriter()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            body = _plan_response(
                {
                    "w1": {
                        "scale_world": 1.0,
                        "scale_by_strategy": {},
                        "deltas": [
                            {"symbol": "BTCUSDT", "delta_qty": -0.25, "venue": "binance"}
                        ],
                    }
                }
            )
            return httpx.Response(200, json=body)
        if request.method == "GET" and request.url.path == "/worlds/w1":
            return httpx.Response(200, json={"world": {"id": "w1", "mode": "simulate"}})
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(handler, commit_log_writer=writer) as ctx:
        resp = await ctx.client.post(
            "/rebalancing/execute?submit=true",
            json=_default_payload(),
            headers={"X-Allow-Live": "true"},
        )
        payload = resp.json()

    assert resp.status_code == 200
    assert payload["submitted"] is True
    assert writer.published
    batch = writer.published[0][1]
    assert batch["world_id"] == "w1"
    assert batch["scope"] == "per_world"
    labels = gw_metrics.rebalance_batches_submitted_total.labels("w1", "per_world")
    assert labels._value.get() == 1
    size = gw_metrics.rebalance_last_batch_size.labels("w1", "per_world")
    assert size._value.get() == 1.0
    ratio = gw_metrics.rebalance_reduce_only_ratio.labels("w1", "per_world")
    assert ratio._value.get() == 1.0
    assert ctx.database.events
    assert ctx.database.events[0][0] == "rebalance:w1"


@pytest.mark.asyncio
async def test_rebalancing_submit_shared_account_requires_toggle(
    gateway_app_factory,
) -> None:
    writer = StubCommitLogWriter()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            body = _plan_response(
                {
                    "w1": {
                        "scale_world": 1.0,
                        "scale_by_strategy": {},
                        "deltas": [
                            {"symbol": "BTCUSDT", "delta_qty": -0.4, "venue": "binance"}
                        ],
                    }
                },
                global_deltas=[{"symbol": "BTCUSDT", "delta_qty": -0.4, "venue": "binance"}],
            )
            return httpx.Response(200, json=body)
        if request.method == "GET" and request.url.path == "/worlds/w1":
            return httpx.Response(200, json={"world": {"id": "w1", "mode": "paper"}})
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(handler, commit_log_writer=writer) as ctx:
        resp = await ctx.client.post(
            "/rebalancing/execute?submit=true&shared_account=true",
            json=_default_payload(),
            headers={"X-Allow-Live": "true"},
        )

    assert resp.status_code == 403
    payload = resp.json()
    assert payload["detail"]["code"] == "E_SHARED_ACCOUNT_DISABLED"
    assert writer.published == []


@pytest.mark.asyncio
async def test_rebalancing_submit_shared_account_global(gateway_app_factory) -> None:
    writer = StubCommitLogWriter()
    policy = SharedAccountPolicyConfig(
        enabled=True,
        max_gross_notional=25000.0,
        max_net_notional=25000.0,
        min_margin_headroom=0.8,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            body = _plan_response(
                {
                    "w1": {
                        "scale_world": 1.0,
                        "scale_by_strategy": {},
                        "deltas": [
                            {"symbol": "BTCUSDT", "delta_qty": -0.4, "venue": "binance"}
                        ],
                    }
                },
                global_deltas=[{"symbol": "BTCUSDT", "delta_qty": -0.4, "venue": "binance"}],
            )
            return httpx.Response(200, json=body)
        if request.method == "GET" and request.url.path == "/worlds/w1":
            return httpx.Response(200, json={"world": {"id": "w1", "mode": "paper"}})
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(
        handler,
        commit_log_writer=writer,
        app_kwargs={"shared_account_policy_config": policy},
    ) as ctx:
        resp = await ctx.client.post(
            "/rebalancing/execute?submit=true&shared_account=true",
            json=_default_payload(),
            headers={"X-Allow-Live": "true"},
        )

    assert resp.status_code == 200
    scopes = {payload["scope"] for _, payload in writer.published}
    assert "global" in scopes
    global_payload = next(p for _, p in writer.published if p["scope"] == "global")
    assert global_payload["world_id"] == "global"
    assert global_payload["shared_account"] is True


@pytest.mark.asyncio
async def test_rebalancing_shared_account_policy_violation(
    gateway_app_factory,
) -> None:
    writer = StubCommitLogWriter()
    policy = SharedAccountPolicyConfig(
        enabled=True,
        max_gross_notional=1000.0,
        max_net_notional=1000.0,
        min_margin_headroom=0.95,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            body = _plan_response(
                {
                    "w1": {
                        "scale_world": 1.0,
                        "scale_by_strategy": {},
                        "deltas": [
                            {"symbol": "BTCUSDT", "delta_qty": -0.4, "venue": "binance"}
                        ],
                    }
                },
                global_deltas=[{"symbol": "BTCUSDT", "delta_qty": -0.4, "venue": "binance"}],
            )
            return httpx.Response(200, json=body)
        if request.method == "GET" and request.url.path == "/worlds/w1":
            return httpx.Response(200, json={"world": {"id": "w1", "mode": "paper"}})
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(
        handler,
        commit_log_writer=writer,
        app_kwargs={"shared_account_policy_config": policy},
    ) as ctx:
        resp = await ctx.client.post(
            "/rebalancing/execute?submit=true&shared_account=true",
            json=_default_payload(),
            headers={"X-Allow-Live": "true"},
        )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "E_SHARED_ACCOUNT_POLICY"
    assert detail["context"]["gross_notional"] > policy.max_gross_notional
    assert writer.published == []


@pytest.mark.asyncio
async def test_rebalancing_submit_per_strategy_branch(gateway_app_factory) -> None:
    writer = StubCommitLogWriter()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            body = _plan_response(
                {
                    "w1": {
                        "scale_world": 1.0,
                        "scale_by_strategy": {},
                        "deltas": [
                            {"symbol": "BTCUSDT", "delta_qty": -0.6, "venue": "binance"}
                        ],
                    }
                }
            )
            return httpx.Response(200, json=body)
        if request.method == "GET" and request.url.path == "/worlds/w1":
            return httpx.Response(200, json={"world": {"id": "w1", "mode": "simulate"}})
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(handler, commit_log_writer=writer) as ctx:
        resp = await ctx.client.post(
            "/rebalancing/execute?submit=true&per_strategy=true",
            json=_default_payload(),
            headers={"X-Allow-Live": "true"},
        )

    assert resp.status_code == 200
    scopes = {payload["scope"] for _, payload in writer.published}
    assert "per_strategy" in scopes
    strat_payload = next(p for _, p in writer.published if p["scope"] == "per_strategy")
    assert strat_payload["orders"]
    assert strat_payload["orders"][0]["strategy_id"] == "s1"
