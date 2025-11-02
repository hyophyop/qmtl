from qmtl.runtime.sdk import Node, StreamInput
from qmtl.runtime.nodesets.steps import (
    pretrade,
    sizing,
    execution,
    order_publish,
    fills,
    portfolio,
    risk,
    timing,
    compose,
)


def test_compose_default_order_and_props():
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda v: {"action": "HOLD"})
    ns = compose(
        signal,
        steps=[
            pretrade(),
            sizing(),
            execution(),
            order_publish(),
            fills(),
            portfolio(),
            risk(),
            timing(),
        ],
    )
    nodes = list(ns)
    assert ns.head is nodes[0]
    assert ns.tail is nodes[-1]
    assert len(nodes) == 8
