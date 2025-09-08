"""CCXT Binance Spot Testnet demo using CcxtBrokerageClient.

Requirements:
- Install ccxt: `uv run --with ccxt -m python qmtl/examples/brokerage_demo/ccxt_binance_sandbox_demo.py`
- Create Binance Spot Testnet API keys at https://testnet.binance.vision

Environment variables:
- BINANCE_API_KEY: your testnet API key
- BINANCE_API_SECRET: your testnet API secret

Notes:
- This demo creates a small LIMIT order and fetches its status.
"""

from __future__ import annotations

import os
from typing import Any

from qmtl.sdk.brokerage_client import CcxtBrokerageClient


def main() -> None:
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        raise SystemExit("Set BINANCE_API_KEY and BINANCE_API_SECRET for testnet")

    client = CcxtBrokerageClient(
        "binance",
        apiKey=api_key,
        secret=api_secret,
        sandbox=True,  # use Binance Spot Testnet endpoints
        options={"defaultType": "spot"},
    )

    # Create a tiny LIMIT order for the demo; adjust quantity/price per testnet rules
    order: dict[str, Any] = {
        "symbol": "BTC/USDT",
        "side": "BUY",
        "type": "limit",
        "quantity": 0.001,
        "limit_price": 10000.0,
        "time_in_force": "GTC",
    }
    resp = client.post_order(order)
    print("create_order:", resp)

    # Try to poll status (may remain open depending on price/liquidity)
    if isinstance(resp, dict):
        order["id"] = resp.get("id") or resp.get("orderId")
    status = client.poll_order_status(order)
    print("status:", status)


if __name__ == "__main__":
    main()

