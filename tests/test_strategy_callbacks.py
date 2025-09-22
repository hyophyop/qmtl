import pytest

from qmtl.sdk import Strategy, StreamInput, ProcessingNode, Runner, buy_signal


class CallbackStrategy(Strategy):
    def __init__(self):
        super().__init__(default_interval="1s", default_period=1)
        self.events = []

    def setup(self):
        src = StreamInput()
        node = ProcessingNode(input=src, compute_fn=lambda v: v, name="n")
        self.add_nodes([src, node])

    def on_start(self):
        self.events.append("start")

    def on_finish(self):
        self.events.append("finish")


class ErrorStrategy(Strategy):
    instances = []

    def __init__(self):
        super().__init__(default_interval="1s", default_period=1)
        self.error = None
        ErrorStrategy.instances.append(self)

    def setup(self):
        src = StreamInput()
        node = ProcessingNode(input=src, compute_fn=lambda v: v, name="n")
        self.add_nodes([src, node])

    def on_error(self, exc):
        self.error = exc


def test_lifecycle_hooks_called(monkeypatch):
    class DummyManager:
        async def resolve_tags(self, offline=False):
            return None

    monkeypatch.setattr(
        "qmtl.sdk.runner.TagManagerService.init",
        lambda self, strategy, world_id=None: DummyManager(),
    )

    strategy = Runner.offline(CallbackStrategy)
    assert strategy.events == ["start", "finish"]


def test_on_error_called(monkeypatch):
    def fail_init(self, strategy, world_id=None):
        raise RuntimeError("fail")

    monkeypatch.setattr("qmtl.sdk.runner.TagManagerService.init", fail_init)

    with pytest.raises(RuntimeError):
        Runner.run(ErrorStrategy, world_id="w", gateway_url=None)

    assert isinstance(ErrorStrategy.instances[-1].error, RuntimeError)


def test_buy_signal_builder():
    assert buy_signal(True, 0.5) == {"action": "BUY", "target_percent": 0.5}
    assert buy_signal(False, 0.5) == {"action": "HOLD"}
