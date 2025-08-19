import importlib

from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node
from strategies.nodes.transforms.publisher import TradeOrderPublisherNode
import qmtl.sdk.runner as runner_module


class FakeKafkaProducer:
    def __init__(self):
        self.messages = []

    def send(self, topic, payload):  # pragma: no cover - simple holder
        self.messages.append((topic, payload))


def test_trade_order_publisher_node_publishes_via_runner():
    importlib.reload(runner_module)
    runner = runner_module.Runner
    producer = FakeKafkaProducer()
    runner.set_kafka_producer(producer)
    runner.set_trade_order_kafka_topic("orders")

    signal_node = Node(name="signal", interval="1s", period=1)
    pub_node = TradeOrderPublisherNode(signal_node, topic="orders")
    view = CacheView({signal_node.node_id: {1: [(0, {"action": "BUY", "size": 2})]}})
    order = pub_node.compute_fn(view)
    runner._postprocess_result(pub_node, order)

    expected = {"side": "BUY", "quantity": 2, "timestamp": 0}
    assert producer.messages == [("orders", expected)]


def test_trade_order_publisher_node_returns_none_for_hold():
    signal_node = Node(name="signal", interval="1s", period=1)
    pub_node = TradeOrderPublisherNode(signal_node, topic="orders")
    view = CacheView({signal_node.node_id: {1: [(0, {"action": "HOLD", "size": 2})]}})
    order = pub_node.compute_fn(view)
    assert order is None
