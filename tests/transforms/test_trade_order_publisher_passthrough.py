from qmtl.sdk import Node, StreamInput
from qmtl.transforms import TradeOrderPublisherNode


def test_publisher_preserves_symbol_type_and_price_mapping():
    src = StreamInput(interval="60s", period=1)

    def make_signal(view):
        return {
            "action": "BUY",
            "size": 2,
            "symbol": "BTC/USDT",
            "type": "limit",
            "price": 30000.0,
            "client_order_id": "abc-123",
        }

    sig = Node(input=src, compute_fn=make_signal, name="signal", interval="60s", period=1)
    pub = TradeOrderPublisherNode(sig)

    # Seed the caches and propagate payload into publisher
    src.feed(src.node_id, src.interval, 60, {"close": 1})
    sig.feed(src.node_id, src.interval, 60, {"close": 1})
    pub.feed(sig.node_id, sig.interval, 60, make_signal(None))

    out = pub.compute_fn(pub.cache.view())
    assert out is not None
    assert out["side"] == "BUY"
    assert out["quantity"] == 2
    assert out["symbol"] == "BTC/USDT"
    assert out["type"] == "limit"
    assert out["limit_price"] == 30000.0
    assert out["client_order_id"] == "abc-123"

