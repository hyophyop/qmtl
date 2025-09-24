from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

from qmtl.runtime.transforms import (
    TradeSignalGeneratorNode,
    threshold_signal_node,
    trade_signal_node,
)


def test_threshold_signal_node():
    assert threshold_signal_node(0.7, long_threshold=0.5, short_threshold=-0.5)["action"] == "BUY"
    assert threshold_signal_node(-0.6, long_threshold=0.5, short_threshold=-0.5)["action"] == "SELL"
    assert threshold_signal_node(0.0, long_threshold=0.5, short_threshold=-0.5)["action"] == "HOLD"


def test_trade_signal_node():
    history = [0.2, 0.7]
    assert trade_signal_node(history, long_threshold=0.5, short_threshold=-0.5)["action"] == "BUY"
    history = [0.2, -0.6]
    assert trade_signal_node(history, long_threshold=0.5, short_threshold=-0.5)["action"] == "SELL"


def test_trade_signal_generator_node():
    history = Node(name="alpha_hist", interval="1s", period=2)
    node = TradeSignalGeneratorNode(history, long_threshold=0.5, short_threshold=-0.5)
    view_buy = CacheView({history.node_id: {history.interval: [(0, [0.2, 0.7])]}})
    assert node.compute_fn(view_buy)["action"] == "BUY"
    view_sell = CacheView({history.node_id: {history.interval: [(0, [0.2, -0.6])]}})
    assert node.compute_fn(view_sell)["action"] == "SELL"
    view_hold = CacheView({history.node_id: {history.interval: [(0, [0.2, 0.0])]}})
    assert node.compute_fn(view_hold)["action"] == "HOLD"


def test_trade_signal_generator_node_with_risk_parameters():
    history = Node(name="alpha_hist", interval="1s", period=1)
    node = TradeSignalGeneratorNode(
        history,
        long_threshold=0.5,
        short_threshold=-0.5,
        size=2.0,
        stop_loss=0.1,
        take_profit=0.3,
    )
    view = CacheView({history.node_id: {history.interval: [(0, [0.7])]}})
    signal = node.compute_fn(view)
    assert signal["size"] == 2.0
    assert signal["stop_loss"] == 0.1
    assert signal["take_profit"] == 0.3
