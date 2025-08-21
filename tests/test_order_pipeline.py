import importlib

import qmtl.sdk.runner as runner_module
from qmtl.sdk.node import Node
from qmtl.transforms import (
    alpha_history_node,
    TradeSignalGeneratorNode,
    TradeOrderPublisherNode,
)


class FakeKafkaProducer:
    def __init__(self):
        self.messages = []

    def send(self, topic, payload):  # pragma: no cover - simple holder
        self.messages.append((topic, payload))


def test_order_pipeline_triggers_http_and_kafka(monkeypatch):
    runner_mod = importlib.reload(runner_module)
    runner = runner_mod.Runner

    posted = {}

    def fake_post(url, json):  # pragma: no cover - minimal stub
        posted["url"] = url
        posted["json"] = json

    monkeypatch.setattr(runner_mod.httpx, "post", fake_post)

    producer = FakeKafkaProducer()
    runner.set_kafka_producer(producer)
    runner.set_trade_order_http_url("http://endpoint")
    runner.set_trade_order_kafka_topic("orders")

    src = Node(name="alpha", interval=1, period=1)
    history = alpha_history_node(src, window=1)
    signal = TradeSignalGeneratorNode(history, long_threshold=0.0, short_threshold=0.0)
    trade = TradeOrderPublisherNode(signal, topic="orders")

    hist_res = runner.feed_queue_data(history, src.node_id, 1, 0, 1.0)
    sig_res = runner.feed_queue_data(signal, history.node_id, 1, 0, hist_res)
    runner.feed_queue_data(trade, signal.node_id, 1, 0, sig_res)

    expected_order = {"side": "BUY", "quantity": 1.0, "timestamp": 0}
    assert posted == {"url": "http://endpoint", "json": expected_order}
    assert producer.messages == [("orders", expected_order)]

    runner.set_trade_order_http_url(None)
    runner.set_trade_order_kafka_topic(None)
    runner.set_kafka_producer(None)
