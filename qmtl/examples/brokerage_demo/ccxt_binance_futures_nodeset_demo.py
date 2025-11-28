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

from qmtl.runtime.sdk import Node, StreamInput
from qmtl.runtime.nodesets.recipes import make_ccxt_futures_nodeset
from qmtl.runtime.sdk.util import parse_interval


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


def _require_interval(node: Node, label: str) -> int:
    interval = getattr(node, "interval", None)
    if interval is None:
        raise ValueError(f"{label} node must define interval seconds for feed()")
    if isinstance(interval, str):
        interval = parse_interval(interval)
    if not isinstance(interval, int):
        raise ValueError(f"{label} node interval must be an int (seconds)")
    return interval


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
    price_interval = _require_interval(price, "price stream")
    signal_interval = _require_interval(signal, "signal")
    price.feed(price.node_id, price_interval, 60, {"close": 1})
    signal.feed(price.node_id, price_interval, 60, {"close": 1})

    nodes = list(nodeset)
    pre, siz, exe, pub = nodes[0], nodes[1], nodes[2], nodes[3]
    pre_interval = _require_interval(pre, "pretrade")
    siz_interval = _require_interval(siz, "sizing")
    exe_interval = _require_interval(exe, "execution")
    pub_interval = _require_interval(pub, "publish")

    order = signal.compute_fn(signal.cache.view())
    pre.feed(signal.node_id, pre_interval, 60, order)
    pre_out = pre.compute_fn(pre.cache.view())
    if pre_out is None:
        raise RuntimeError("pretrade step returned no data")

    siz.feed(pre.node_id, siz_interval, 60, pre_out)
    siz_out = siz.compute_fn(siz.cache.view())
    if siz_out is None:
        raise RuntimeError("sizing step returned no data")

    exe.feed(siz.node_id, exe_interval, 60, siz_out)
    exe_out = exe.compute_fn(exe.cache.view())
    if exe_out is None:
        raise RuntimeError("execution step returned no data")

    pub.feed(exe.node_id, pub_interval, 60, exe_out)
    published = pub.compute_fn(pub.cache.view())
    print("submitted order:", published)


if __name__ == "__main__":
    main()
