from qmtl.sdk import Node, StreamInput
from qmtl.nodesets.recipes import make_ccxt_spot_nodeset


def test_ccxt_nodeset_exec_carries_symbol_and_defaults():
    price = StreamInput(interval="60s", period=1)

    def make_signal(view):
        return {
            "action": "BUY",
            "size": 1,
            "symbol": "BTC/USDT",
            "type": "limit",
            "price": 100.0,
        }

    signal = Node(input=price, compute_fn=make_signal, name="sig", interval="60s", period=1)
    ns = make_ccxt_spot_nodeset(
        signal,
        "world",
        exchange_id="binance",
        sandbox=False,
        reduce_only=True,
    )

    # Seed chain: emulate per-node ingestion and compute
    price.feed(price.node_id, price.interval, 60, {"close": 1})
    signal.feed(price.node_id, price.interval, 60, {"close": 1})

    # Execute the stubbed chain: pretrade -> sizing -> exec (CCXT)
    pre = ns.pretrade
    siz = ns.sizing
    exe = ns.execution

    pre.feed(signal.node_id, signal.interval, 60, make_signal(None))
    pre_out = pre.compute_fn(pre.cache.view())
    assert pre_out is not None

    siz.feed(pre.node_id, pre.interval, 60, pre_out)
    siz_out = siz.compute_fn(siz.cache.view())
    assert siz_out is not None

    exe.feed(siz.node_id, siz.interval, 60, siz_out)
    out = exe.compute_fn(exe.cache.view())

    assert out is not None
    assert out["symbol"] == "BTC/USDT"
    assert out["time_in_force"] == "GTC"
    assert out["reduce_only"] is True
    assert out["type"] == "limit"
    assert out.get("limit_price", out.get("price")) == 100.0
