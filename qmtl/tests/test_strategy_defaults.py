import pytest
from qmtl.sdk import Strategy, StreamInput, ProcessingNode


class DefaultStrategy(Strategy):
    def __init__(self):
        super().__init__(default_interval="60s", default_period=2)

    def setup(self):
        src = StreamInput()
        node = ProcessingNode(input=src, compute_fn=lambda v: v, name="n")
        self.add_nodes([src, node])


def test_defaults_applied():
    strat = DefaultStrategy()
    strat.setup()
    src, node = strat.nodes
    assert src.interval == 60
    assert src.period == 2
    assert node.interval == 60
    assert node.period == 2
    assert src.cache.window_size == 2
    assert node.cache.window_size == 2


class OverrideStrategy(Strategy):
    def __init__(self):
        super().__init__(default_interval="60s", default_period=2)

    def setup(self):
        src = StreamInput(interval="30s", period=1)
        node = ProcessingNode(input=src, compute_fn=lambda v: v, name="n", interval="30s", period=3)
        self.add_nodes([src, node])


def test_override_values():
    strat = OverrideStrategy()
    strat.setup()
    src, node = strat.nodes
    assert src.interval == 30
    assert src.period == 1
    assert node.interval == 30
    assert node.period == 3


class MissingDefaultsStrategy(Strategy):
    def setup(self):
        src = StreamInput()
        node = ProcessingNode(input=src, compute_fn=lambda v: v, name="n")
        self.add_nodes([src, node])


def test_missing_defaults_error():
    strat = MissingDefaultsStrategy()
    with pytest.raises(ValueError):
        strat.setup()
