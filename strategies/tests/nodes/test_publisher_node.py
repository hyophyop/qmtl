import importlib

from strategies.nodes.transforms.publisher import publisher_node
import qmtl.sdk.runner as runner_module


class FakeKafkaProducer:
    def __init__(self):
        self.messages = []

    def send(self, topic, payload):  # pragma: no cover - simple holder
        self.messages.append((topic, payload))


def test_publisher_node_publishes_via_runner():
    importlib.reload(runner_module)
    runner = runner_module.Runner
    producer = FakeKafkaProducer()
    runner.set_kafka_producer(producer)
    signal = {"action": "BUY"}
    result = publisher_node(signal, topic="orders")
    runner._publish_result(result)
    assert producer.messages == [("orders", signal)]
