"""CCXT Fee Profile Demo (Spot & Futures)

This example shows how to build a BrokerageModel using ``make_ccxt_brokerage``
for both spot and futures exchanges and simulate a few trades to observe fee
application differences between taker (market) and maker (limit) orders.

By default, the demo uses conservative fallback fees (no network, no ccxt
required). To enable ccxt-based fee detection, set env ``DETECT_FEES=1``.
Optionally set ``SANDBOX=1`` to prefer exchange testnet endpoints when
supported.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from qmtl.brokerage import (
    Account,
    Order,
    OrderType,
    TimeInForce,
)
from qmtl.brokerage.ccxt_profile import make_ccxt_brokerage


def build_spot_model(
    exchange_id: str = "binance",
    *,
    symbol: str = "BTC/USDT",
    detect_fees: bool = False,
    sandbox: bool = False,
    defaults: tuple[float, float] = (0.0002, 0.0007),
):
    return make_ccxt_brokerage(
        exchange_id,
        product="spot",
        symbol=symbol,
        sandbox=sandbox,
        detect_fees=detect_fees,
        defaults=defaults,
    )


def build_futures_model(
    exchange_id: str = "binanceusdm",
    *,
    symbol: str = "BTC/USDT",
    detect_fees: bool = False,
    sandbox: bool = False,
    defaults: tuple[float, float] = (0.0004, 0.0008),
):
    return make_ccxt_brokerage(
        exchange_id,
        product="futures",
        symbol=symbol,
        sandbox=sandbox,
        detect_fees=detect_fees,
        defaults=defaults,
    )


def _exec(model, order: Order, *, market_price: float, cash: float = 100_000.0):
    acct = Account(cash=cash, base_currency="USDT")
    fill = model.execute_order(acct, order, market_price)
    return {
        "order": {
            "symbol": order.symbol,
            "type": order.type.value,
            "tif": order.tif.value,
            "qty": order.quantity,
            "price": order.price,
            "limit": order.limit_price,
        },
        "fill": {"qty": fill.quantity, "price": fill.price, "fee": fill.fee},
        "cash_after": acct.cash,
    }


def run_demo() -> dict[str, Any]:
    detect = os.getenv("DETECT_FEES", "0") in {"1", "true", "TRUE"}
    sandbox = os.getenv("SANDBOX", "0") in {"1", "true", "TRUE"}
    spot_symbol = os.getenv("SPOT_SYMBOL", "BTC/USDT")
    fut_symbol = os.getenv("FUT_SYMBOL", "BTC/USDT")

    spot = build_spot_model("binance", symbol=spot_symbol, detect_fees=detect, sandbox=sandbox)
    fut = build_futures_model("binanceusdm", symbol=fut_symbol, detect_fees=detect, sandbox=sandbox)

    # Simulate a few orders to illustrate maker/taker fee application.
    spot_market_buy = Order(symbol=spot_symbol, quantity=1, price=50_000.0, type=OrderType.MARKET, tif=TimeInForce.DAY)
    spot_limit_buy = Order(
        symbol=spot_symbol,
        quantity=1,
        price=50_000.0,
        type=OrderType.LIMIT,
        limit_price=49_900.0,
        tif=TimeInForce.GTC,
    )
    fut_market_sell = Order(symbol=fut_symbol, quantity=-2, price=30_000.0, type=OrderType.MARKET, tif=TimeInForce.DAY)
    fut_limit_sell = Order(
        symbol=fut_symbol,
        quantity=-2,
        price=30_000.0,
        type=OrderType.LIMIT,
        limit_price=30_100.0,
        tif=TimeInForce.GTC,
    )

    results = {
        "spot": {
            "maker_rate": getattr(spot.fee_model, "maker_rate", None),
            "taker_rate": getattr(spot.fee_model, "taker_rate", None),
            "market_buy": _exec(spot, spot_market_buy, market_price=50_000.0),
            "limit_buy": _exec(spot, spot_limit_buy, market_price=49_900.0),
        },
        "futures": {
            "maker_rate": getattr(fut.fee_model, "maker_rate", None),
            "taker_rate": getattr(fut.fee_model, "taker_rate", None),
            "market_sell": _exec(fut, fut_market_sell, market_price=30_000.0),
            "limit_sell": _exec(fut, fut_limit_sell, market_price=30_100.0),
        },
        "detect_fees": detect,
        "sandbox": sandbox,
    }
    return results


if __name__ == "__main__":  # pragma: no cover - manual demo
    import json

    out = run_demo()
    print(json.dumps(out, indent=2, sort_keys=True))

