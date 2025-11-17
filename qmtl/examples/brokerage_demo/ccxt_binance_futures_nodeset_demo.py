"""CCXT Binance Futures Node Set demo that submits a testnet order via the recipe.

Run with:

```
uv run --with ccxt -m python qmtl/examples/brokerage_demo/ccxt_binance_futures_nodeset_demo.py
```

Environment variables:
- BINANCE_FUT_API_KEY / BINANCE_FUT_API_SECRET: Binance Futures Testnet credentials

The script wires a minimal signal through ``make_ccxt_futures_nodeset`` and executes a LIMIT order.
Adjust quantity/price per exchange filters before running in live environments.
"""

from __future__ import annotations

import os
from typing import Any

from qmtl.runtime.sdk import Node, StreamInput  # type: ignore[import-untyped]
from qmtl.runtime.nodesets.recipes import make_ccxt_futures_nodeset


def _make_signal(symbol: str) -> Node:
    price = StreamInput(interval=60, period=1)

    def compute(view: Any) -> dict[str, Any]:
        return {
            "action": "BUY",
            "size": 1.0,
            "symbol": symbol,
            "type": "limit",
            "price": 10000.0,
        }

    node = Node(input=price, compute_fn=compute, name="demo_signal", interval="60s", period=1)
    return node


def main() -> None:
    api_key = os.getenv("BINANCE_FUT_API_KEY")
    api_secret = os.getenv("BINANCE_FUT_API_SECRET")
    if not api_key or not api_secret:
        raise SystemExit("Set BINANCE_FUT_API_KEY and BINANCE_FUT_API_SECRET for futures testnet")

    symbol = "BTC/USDT"
    signal = _make_signal(symbol)
    nodeset = make_ccxt_futures_nodeset(
        signal,
        "demo-world",
        exchange_id="binanceusdm",
        sandbox=True,
        apiKey=api_key,
        secret=api_secret,
        leverage=5,
        margin_mode="cross",
        hedge_mode=True,
    )

    # Prime upstream nodes so the recipe can process the order payload
    price = signal.input  # StreamInput from _make_signal
    assert isinstance(price, StreamInput)
    price.feed(price.node_id, price.interval or 0, 60, {"close": 1})
    signal.feed(price.node_id, price.interval or 0, 60, {"close": 1})

    nodes = list(nodeset)
    pre, siz, exe, pub = nodes[0], nodes[1], nodes[2], nodes[3]

    order = signal.compute_fn(signal.cache.view())
    pre.feed(signal.node_id, signal.interval, 60, order)
    pre_out = pre.compute_fn(pre.cache.view())
    if pre_out is None:
        raise RuntimeError("pretrade step returned no data")

    siz.feed(pre.node_id, pre.interval, 60, pre_out)
    siz_out = siz.compute_fn(siz.cache.view())
    if siz_out is None:
        raise RuntimeError("sizing step returned no data")

    exe.feed(siz.node_id, siz.interval, 60, siz_out)
    exe_out = exe.compute_fn(exe.cache.view())
    if exe_out is None:
        raise RuntimeError("execution step returned no data")

    pub.feed(exe.node_id, exe.interval, 60, exe_out)
    published = pub.compute_fn(pub.cache.view())
    print("submitted order:", published)


if __name__ == "__main__":
    main()

