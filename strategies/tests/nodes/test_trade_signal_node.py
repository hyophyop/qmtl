from strategies.nodes.transforms.trade_signal import (
    threshold_signal_node,
    trade_signal_node,
)


def test_threshold_signal_node():
    assert threshold_signal_node(0.7, long_threshold=0.5, short_threshold=-0.5)["action"] == "BUY"
    assert threshold_signal_node(-0.6, long_threshold=0.5, short_threshold=-0.5)["action"] == "SELL"
    assert threshold_signal_node(0.0, long_threshold=0.5, short_threshold=-0.5)["action"] == "HOLD"


def test_trade_signal_node():
    assert (
        trade_signal_node([0.2, 0.7], long_threshold=0.5, short_threshold=-0.5)["action"]
        == "BUY"
    )
    assert (
        trade_signal_node([0.2, -0.6], long_threshold=0.5, short_threshold=-0.5)["action"]
        == "SELL"
    )
    assert (
        trade_signal_node([0.2, 0.0], long_threshold=0.5, short_threshold=-0.5)["action"]
        == "HOLD"
    )


def test_trade_signal_node_with_risk_parameters():
    signal = trade_signal_node(
        [0.7],
        long_threshold=0.5,
        short_threshold=-0.5,
        size=2.0,
        stop_loss=0.1,
        take_profit=0.3,
    )
    assert signal["size"] == 2.0
    assert signal["stop_loss"] == 0.1
    assert signal["take_profit"] == 0.3
