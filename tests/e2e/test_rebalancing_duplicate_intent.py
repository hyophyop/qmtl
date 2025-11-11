import pytest
import httpx

from qmtl.services.worldservice.api import create_app as create_world_app
from qmtl.services.worldservice.storage import Storage
from qmtl.services.gateway.api import create_app as create_gateway_app
from qmtl.services.gateway.world_client import WorldServiceClient
from tests.qmtl.services.gateway.helpers import StubGatewayDatabase


@pytest.mark.asyncio
async def test_duplicate_intent_rebalance_scaling(fake_redis):
    await fake_redis.flushdb()

    storage = Storage()
    world_app = create_world_app(storage=storage)

    payload = {
        "total_equity": 1_000_000.0,
        "world_alloc_before": {"world-a": 0.3},
        "world_alloc_after": {"world-a": 0.2},
        "strategy_alloc_before_total": {
            "world-a": {"strat-1": 0.15, "strat-2": 0.15},
        },
        "strategy_alloc_after_total": {
            "world-a": {"strat-1": 0.10, "strat-2": 0.10},
        },
        "positions": [
            {
                "world_id": "world-a",
                "strategy_id": "strat-1",
                "symbol": "BTCUSDT",
                "qty": 0.6,
                "mark": 60_000.0,
                "venue": "binance",
            },
            {
                "world_id": "world-a",
                "strategy_id": "strat-2",
                "symbol": "BTCUSDT",
                "qty": 0.9,
                "mark": 60_000.0,
                "venue": "binance",
            },
        ],
        "min_trade_notional": 0.0,
        "mode": "scaling",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=world_app),
        base_url="http://world",
    ) as world_api:
        apply_resp = await world_api.post("/rebalancing/apply", json=payload)
        assert apply_resp.status_code == 200
        apply_data = apply_resp.json()

    plan = apply_data["per_world"]["world-a"]
    assert plan["scale_world"] == pytest.approx(2 / 3, rel=1e-9)
    assert plan["scale_by_strategy"]["strat-1"] == pytest.approx(2 / 3, rel=1e-9)
    assert plan["scale_by_strategy"]["strat-2"] == pytest.approx(2 / 3, rel=1e-9)
    assert len(plan["deltas"]) == 1
    delta = plan["deltas"][0]
    assert delta["symbol"] == "BTCUSDT"
    assert delta["venue"] == "binance"
    assert delta["delta_qty"] == pytest.approx(-0.5, abs=1e-9)

    assert apply_data["global_deltas"]
    assert apply_data["global_deltas"][0]["delta_qty"] == pytest.approx(-0.5, abs=1e-9)

    async with httpx.ASGITransport(app=world_app) as world_transport:
        async with httpx.AsyncClient(
            transport=world_transport,
            base_url="http://world",
        ) as world_client_api:
            world_client = WorldServiceClient("http://world", client=world_client_api)

            gateway_app = create_gateway_app(
                redis_client=fake_redis,
                database=StubGatewayDatabase(),
                enable_background=False,
                world_client=world_client,
            )

            async with httpx.ASGITransport(app=gateway_app) as gateway_transport:
                async with httpx.AsyncClient(
                    transport=gateway_transport,
                    base_url="http://gateway",
                ) as gateway_api:
                    execute_resp = await gateway_api.post(
                        "/rebalancing/execute?per_strategy=true",
                        json=payload,
                    )
                    assert execute_resp.status_code == 200
                    execute_data = execute_resp.json()

    per_world_orders = execute_data["orders_per_world"]["world-a"]
    assert len(per_world_orders) == 1
    world_order = per_world_orders[0]
    assert world_order["symbol"] == "BTCUSDT"
    assert world_order["quantity"] == pytest.approx(-0.5, abs=1e-9)
    assert world_order["side"] == "sell"
    assert world_order["reduce_only"] is True

    per_strategy_orders = execute_data["orders_per_strategy"]
    assert len(per_strategy_orders) == 2
    qty_by_strategy = {
        item["strategy_id"]: item["order"]["quantity"] for item in per_strategy_orders
    }
    assert qty_by_strategy["strat-1"] == pytest.approx(-0.2, abs=1e-9)
    assert qty_by_strategy["strat-2"] == pytest.approx(-0.3, abs=1e-9)
    assert all(item["order"]["reduce_only"] is True for item in per_strategy_orders)

    assert execute_data["submitted"] is False
    assert "orders_global" not in execute_data or not execute_data["orders_global"]

