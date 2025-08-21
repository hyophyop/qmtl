"""Test basic alpha-to-order flow without full pipeline."""

from qmtl.transforms import trade_signal_node
from qmtl.transforms.publisher import publisher_node
from strategies.nodes.generators import sample_generator
from strategies.nodes.indicators import sample_indicator


def test_alpha_signal_strategy_executes():
    data = sample_generator()
    alpha = sample_indicator(data)
    signal = trade_signal_node([alpha], long_threshold=0.0, short_threshold=0.0, size=1.0)
    topic, out_signal = publisher_node(signal, topic="orders")
    assert topic == "orders"
    assert out_signal["action"] == "BUY"
