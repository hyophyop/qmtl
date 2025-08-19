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
