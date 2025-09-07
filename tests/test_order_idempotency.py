import importlib

import qmtl.sdk.runner as runner_module
from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node
from qmtl.transforms import TradeOrderPublisherNode


class FakeKafkaProducer:
    def __init__(self):
        self.messages = []
    def send(self, topic, payload):  # pragma: no cover - simple holder
        self.messages.append((topic, payload))


def test_order_idempotency_suppresses_duplicates(monkeypatch):
    # Reload runner to get a clean class state
    runner = importlib.reload(runner_module).Runner
    runner.reset_trade_order_dedup()

    # Set Kafka producer and topic target
    producer = FakeKafkaProducer()
    runner.set_kafka_producer(producer)  # type: ignore[attr-defined]
    runner.set_trade_order_kafka_topic("orders")  # type: ignore[attr-defined]

    # Build a publisher node emitting the same order twice
    signal_node = Node(name="signal", interval="1s", period=1)
    pub_node = TradeOrderPublisherNode(signal_node)

    # Simulate a signal that results in a BUY order
    signal_payload = {"action": "BUY", "size": 1}
    # Second compute uses the same payload (duplicate)
    view = CacheView({signal_node.node_id: {1: [(123456, signal_payload)]}})

    # First publish should pass
    out = pub_node.compute_fn(view)
    runner._postprocess_result(pub_node, out)

    # Second publish with identical payload should be suppressed
    out2 = pub_node.compute_fn(view)
    runner._postprocess_result(pub_node, out2)

    expected = {"side": "BUY", "quantity": 1, "timestamp": 123456}
    assert producer.messages == [("orders", expected)]
