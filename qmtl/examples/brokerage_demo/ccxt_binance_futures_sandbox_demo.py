"""CCXT Binance USDT-M Futures Testnet demo using FuturesCcxtBrokerageClient.

Requirements:
- Install ccxt: `uv run --with ccxt -m python qmtl/examples/brokerage_demo/ccxt_binance_futures_sandbox_demo.py`
- Create Binance Futures Testnet API keys at https://testnet.binancefuture.com

Environment variables:
- BINANCE_FUT_API_KEY: your testnet API key
- BINANCE_FUT_API_SECRET: your testnet API secret

Notes:
- This demo submits a small LIMIT order; adjust price/qty per testnet filters.
- Demonstrates `reduce_only`, `position_side`, and per-order leverage changes.
"""

from __future__ import annotations

import os
from typing import Any

from qmtl.sdk.brokerage_client import FuturesCcxtBrokerageClient


def main() -> None:
    api_key = os.getenv("BINANCE_FUT_API_KEY")
    api_secret = os.getenv("BINANCE_FUT_API_SECRET")
    if not api_key or not api_secret:
        raise SystemExit("Set BINANCE_FUT_API_KEY and BINANCE_FUT_API_SECRET for futures testnet")

    symbol = "BTC/USDT"
    client = FuturesCcxtBrokerageClient(
        "binanceusdm",
        symbol=symbol,
        leverage=5,
        margin_mode="cross",
        hedge_mode=True,
        apiKey=api_key,
        secret=api_secret,
        sandbox=True,
    )

    order: dict[str, Any] = {
        "symbol": symbol,
        "side": "BUY",
        "type": "limit",
        "quantity": 0.001,
        "limit_price": 10000.0,
        "time_in_force": "GTC",
        "reduce_only": False,
        "position_side": "LONG",
        "leverage": 10,
    }
    resp = client.post_order(order)
    print("create_order:", resp)

    if isinstance(resp, dict):
        order["id"] = resp.get("id") or resp.get("orderId")
    status = client.poll_order_status(order)
    print("status:", status)


if __name__ == "__main__":
    main()

