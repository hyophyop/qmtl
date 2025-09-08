from qmtl.sdk import Node, StreamInput
from qmtl.brokerage.ccxt_spot_nodeset import CcxtSpotNodeSet


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
    pub, opts, exe = CcxtSpotNodeSet.attach(
        signal,
        "world",
        exchange_id="binance",
        sandbox=False,
        reduce_only=True,
    )

    # Seed chain: emulate per-node ingestion and compute
    price.feed(price.node_id, price.interval, 60, {"close": 1})
    signal.feed(price.node_id, price.interval, 60, {"close": 1})

    pub.feed(signal.node_id, signal.interval, 60, make_signal(None))
    pub_out = pub.compute_fn(pub.cache.view())
    assert pub_out is not None

    opts.feed(pub.node_id, pub.interval, 60, pub_out)
    opts_out = opts.compute_fn(opts.cache.view())
    assert opts_out is not None

    exe.feed(opts.node_id, opts.interval, 60, opts_out)
    out = exe.compute_fn(exe.cache.view())

    assert out is not None
    assert out["symbol"] == "BTC/USDT"
    assert out["time_in_force"] == "GTC"
    assert out["reduce_only"] is True
    assert out["type"] == "limit"
    assert out["limit_price"] == 100.0

