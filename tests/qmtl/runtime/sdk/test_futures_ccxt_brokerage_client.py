from __future__ import annotations

import sys
import types
from typing import Any

from qmtl.runtime.sdk.brokerage_client import FuturesCcxtBrokerageClient


def test_futures_ccxt_brokerage_client_builds_order_payload(monkeypatch):
    module = types.SimpleNamespace()

    class _FakeExchange:
        def __init__(self, config: dict[str, Any]) -> None:
            module.instance = self
            self.config = config
            self.calls: list[dict[str, Any]] = []
            self.position_modes: list[bool] = []
            self.margin_calls: list[tuple[str, str]] = []
            self.leverage_calls: list[tuple[int, str]] = []

        def set_sandbox_mode(self, value: bool) -> None:
            self.sandbox = value

        def setSandboxMode(self, value: bool) -> None:
            self.sandbox = value

        def set_position_mode(self, value: bool) -> None:
            self.position_modes.append(value)

        def set_margin_mode(self, mode: str, symbol: str) -> None:
            self.margin_calls.append((mode, symbol))

        def set_leverage(self, value: int, symbol: str) -> None:
            self.leverage_calls.append((value, symbol))

        def create_order(self, symbol: str, typ: str, side: str, amount: Any, price: Any, params: dict[str, Any]) -> dict[str, Any]:
            call = {
                "symbol": symbol,
                "type": typ,
                "side": side,
                "amount": amount,
                "price": price,
                "params": params,
            }
            self.calls.append(call)
            return {"id": "0", "params": params}

        def fetch_order(self, *_: Any) -> None:
            return None

        def cancel_order(self, *_: Any) -> None:
            return None

    module.binanceusdm = _FakeExchange
    monkeypatch.setitem(sys.modules, "ccxt", module)

    client = FuturesCcxtBrokerageClient(
        symbol="BTC/USDT",
        leverage=8,
        margin_mode="isolated",
        hedge_mode=True,
        sandbox=True,
    )
    response = client.post_order({
        "symbol": "BTC/USDT",
        "side": "BUY",
        "type": "limit",
        "quantity": 1,
        "limit_price": 123.4,
        "time_in_force": "gtc",
        "reduce_only": True,
        "position_side": "long",
        "client_order_id": "cid-1",
        "leverage": 3,
    })

    assert response["id"] == "0"
    exchange = module.instance
    assert exchange.calls
    params = exchange.calls[0]["params"]
    assert params["timeInForce"] == "GTC"
    assert params["reduceOnly"] is True
    assert params["positionSide"] == "LONG"
    assert params["newClientOrderId"] == "cid-1"
    assert exchange.margin_calls[-1] == ("ISOLATED", "BTC/USDT")
    assert (3, "BTC/USDT") in exchange.leverage_calls


def test_symbol_defaults_retry_after_init_failure(monkeypatch):
    module = types.SimpleNamespace()

    class _FlakyExchange:
        def __init__(self, _config: dict[str, Any]) -> None:
            module.instance = self
            self.margin_attempts = 0
            self.margin_calls: list[tuple[str, str]] = []
            self.leverage_calls: list[tuple[int, str]] = []
            self.orders_posted = 0

        def set_margin_mode(self, mode: str, symbol: str) -> None:
            self.margin_attempts += 1
            if self.margin_attempts == 1:
                raise RuntimeError("transient failure")
            self.margin_calls.append((mode, symbol))

        def set_leverage(self, value: int, symbol: str) -> None:
            self.leverage_calls.append((value, symbol))

        def create_order(
            self, symbol: str, typ: str, side: str, amount: Any, price: Any, params: dict[str, Any]
        ) -> dict[str, Any]:
            self.orders_posted += 1
            return {"id": str(self.orders_posted), "params": params}

    module.binanceusdm = _FlakyExchange
    monkeypatch.setitem(sys.modules, "ccxt", module)

    client = FuturesCcxtBrokerageClient(
        symbol="BTC/USDT",
        leverage=5,
        margin_mode="isolated",
    )

    exchange = module.instance
    assert exchange.margin_attempts == 1
    assert "BTC/USDT" not in client._symbol_prefs_applied  # type: ignore[attr-defined]

    client.post_order({
        "symbol": "BTC/USDT",
        "side": "buy",
        "quantity": 1,
    })

    assert exchange.margin_calls == [("ISOLATED", "BTC/USDT")]
    assert exchange.leverage_calls == [(5, "BTC/USDT"), (5, "BTC/USDT")]
    assert "BTC/USDT" in client._symbol_prefs_applied  # type: ignore[attr-defined]
