from qmtl.sdk import Node, StreamInput
from qmtl.nodesets.steps import pretrade, sizing, execution, fills, portfolio, risk, timing, compose


def test_compose_default_order_and_props():
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda v: {"action": "HOLD"})
    ns = compose(signal, steps=[pretrade(), sizing(), execution(), fills(), portfolio(), risk(), timing()])
    nodes = list(ns)
    assert nodes[0] is ns.pretrade
    assert nodes[-1] is ns.timing
    assert ns.head is ns.pretrade and ns.tail is ns.timing
    assert len(nodes) == 7

