import json
from pathlib import Path

import jsonschema


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("Could not locate repository root from test path")


SCHEMAS_DIR = _repo_root() / "docs" / "en" / "reference" / "schemas"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text())


def test_examples_conform_to_json_schemas():
    order_payload = {
        "world_id": "arch_world",
        "strategy_id": "strat_001",
        "correlation_id": "ord-20230907-0001",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "type": "limit",
        "quantity": 0.01,
        "limit_price": 25000.0,
        "stop_price": None,
        "time_in_force": "GTC",
        "client_order_id": "c-abc123",
        "timestamp": 1694102400000,
        "reduce_only": False,
        "position_side": None,
        "metadata": {"source": "node_set/binance_spot"},
        "extra": "ok",
    }
    order_ack = {
        "order_id": "exch-7890",
        "client_order_id": "c-abc123",
        "status": "accepted",
        "reason": None,
        "broker": "binance",
        "raw": {"provider_payload": "..."},
        "example": True,
    }
    fill = {
        "order_id": "exch-7890",
        "client_order_id": "c-abc123",
        "correlation_id": "ord-20230907-0001",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "quantity": 0.005,
        "price": 24990.5,
        "commission": 0.02,
        "slippage": 0.5,
        "market_impact": 0.0,
        "tif": "GTC",
        "fill_time": 1694102401100,
        "status": "partially_filled",
        "seq": 12,
        "etag": "w1-s1-7890-12",
        "note": "ok",
    }
    snapshot = {
        "world_id": "arch_world",
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"BTC/USDT": 0.6, "ETH/USDT": 0.4},
        "provenance": {"actor": "gateway", "stage": "paper"},
        "ttl_sec": 900,
        "debug": 1,
    }

    jsonschema.validate(order_payload, _load_schema("order_payload.schema.json"))
    jsonschema.validate(order_ack, _load_schema("order_ack.schema.json"))
    jsonschema.validate(fill, _load_schema("execution_fill_event.schema.json"))
    jsonschema.validate(snapshot, _load_schema("portfolio_snapshot.schema.json"))
