from strategies.nodes.transforms.trade_signal import threshold_signal_node


def test_threshold_signal_node():
    assert threshold_signal_node(0.7, long_threshold=0.5, short_threshold=-0.5)["action"] == "BUY"
    assert threshold_signal_node(-0.6, long_threshold=0.5, short_threshold=-0.5)["action"] == "SELL"
    assert threshold_signal_node(0.0, long_threshold=0.5, short_threshold=-0.5)["action"] == "HOLD"
