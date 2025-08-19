from typing import Any

from qmtl.sdk.runner import Runner
from qmtl.sdk.node import Node
from qmtl.sdk.strategy import Strategy


class AlphaPerformanceNode(Node):
    pass


class TradeOrderPublisherNode(Node):
    pass


class DummyStrategy(Strategy):
    def setup(self) -> None:
        self.source = Node(name="src", interval=1, period=1)
        self.alpha = AlphaPerformanceNode(
            self.source,
            compute_fn=lambda view: {"metric": 1},
            interval=1,
            period=1,
        )
        self.trade = TradeOrderPublisherNode(
            self.alpha,
            compute_fn=lambda view: {"order": "BUY"},
            interval=1,
            period=1,
        )
        self.add_nodes([self.source, self.alpha, self.trade])


def _trigger(strategy: DummyStrategy) -> None:
    Runner.feed_queue_data(strategy.alpha, strategy.source.node_id, 1, 0, {})
    Runner.feed_queue_data(strategy.trade, strategy.alpha.node_id, 1, 0, {})


def test_backtest_hooks(monkeypatch):
    collected = []
    orders = []

    def fake_alpha(result):
        collected.append(result)
    def fake_order(order):
        orders.append(order)

    async def fake_gateway(**kwargs):
        return {}

    class DummyManager:
        async def resolve_tags(self, offline=False):
            pass

    monkeypatch.setattr("qmtl.sdk.runner.Runner._post_gateway_async", staticmethod(fake_gateway))
    monkeypatch.setattr(Runner, "_init_tag_manager", lambda s, u: DummyManager())
    monkeypatch.setattr("qmtl.sdk.runner.Runner._handle_alpha_performance", staticmethod(fake_alpha))
    monkeypatch.setattr("qmtl.sdk.runner.Runner._handle_trade_order", staticmethod(fake_order))

    strategy = Runner.backtest(DummyStrategy, start_time=0, end_time=1, gateway_url="http://gw")
    _trigger(strategy)

    Runner.set_trade_order_http_url(None)
    Runner.set_trade_order_kafka_topic(None)
    Runner.set_kafka_producer(None)

    assert collected == [{"metric": 1}]
    assert orders == [{"order": "BUY"}]


class FakeKafkaProducer:
    def __init__(self):
        self.messages = []

    def send(self, topic, payload):  # pragma: no cover - simple holder
        self.messages.append((topic, payload))


def test_handle_trade_order_http_and_kafka(monkeypatch):
    posted: dict[str, Any] = {}

    def fake_post(url, json):  # pragma: no cover - minimal stub
        posted["url"] = url
        posted["json"] = json

    import importlib
    import qmtl.sdk.runner as runner_module
    runner_module = importlib.reload(runner_module)
    monkeypatch.setattr(runner_module.httpx, "post", fake_post)
    assert runner_module.httpx.post is fake_post

    runner = runner_module.Runner
    producer = FakeKafkaProducer()
    runner.set_kafka_producer(producer)
    runner.set_trade_order_http_url("http://endpoint")
    runner.set_trade_order_kafka_topic("orders")

    order = {"side": "BUY", "quantity": 1}
    runner._handle_trade_order(order)

    assert posted == {"url": "http://endpoint", "json": order}
    assert producer.messages == [("orders", order)]

    runner.set_trade_order_http_url(None)
    runner.set_trade_order_kafka_topic(None)
    runner.set_kafka_producer(None)


def test_live_hooks(monkeypatch):
    collected = []
    orders = []

    def fake_alpha(result):
        collected.append(result)
    def fake_order(order):
        orders.append(order)

    async def fake_gateway(**kwargs):
        return {}

    class DummyManager:
        async def resolve_tags(self, offline=False):
            pass

    monkeypatch.setattr("qmtl.sdk.runner.Runner._post_gateway_async", staticmethod(fake_gateway))
    monkeypatch.setattr("qmtl.sdk.runner.Runner.run_pipeline", staticmethod(lambda s: None))
    monkeypatch.setattr(Runner, "_init_tag_manager", lambda s, u: DummyManager())
    monkeypatch.setattr("qmtl.sdk.runner.Runner._handle_alpha_performance", staticmethod(fake_alpha))
    monkeypatch.setattr("qmtl.sdk.runner.Runner._handle_trade_order", staticmethod(fake_order))

    strategy = Runner.live(DummyStrategy, gateway_url="http://gw", offline=True)
    _trigger(strategy)

    Runner.set_trade_order_http_url(None)
    Runner.set_trade_order_kafka_topic(None)
    Runner.set_kafka_producer(None)

    assert collected == [{"metric": 1}]
    assert orders == [{"order": "BUY"}]


def test_handle_alpha_performance_updates_metrics():
    from qmtl.sdk import metrics as sdk_metrics

    sdk_metrics.reset_metrics()
    Runner._handle_alpha_performance({"sharpe": 1.23, "max_drawdown": -0.5})
    assert sdk_metrics.alpha_sharpe._val == 1.23
    assert sdk_metrics.alpha_max_drawdown._val == -0.5
