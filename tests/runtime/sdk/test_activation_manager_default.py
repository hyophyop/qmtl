import importlib

import qmtl.runtime.sdk.runner as runner_module
from qmtl.runtime.sdk.activation_manager import ActivationManager


class FakeKafkaProducer:
    def __init__(self) -> None:
        self.messages = []

    def send(self, topic, payload):
        self.messages.append((topic, payload))


def test_runner_blocks_without_activation():
    importlib.reload(runner_module)
    from qmtl.runtime.sdk.runner import Runner

    producer = FakeKafkaProducer()
    Runner.set_kafka_producer(producer)
    Runner.set_trade_order_kafka_topic("orders")

    am = ActivationManager()
    Runner.set_activation_manager(am)

    assert am.is_stale()
    assert not am.allow_side("BUY")
    assert not am.allow_side("SELL")

    Runner._handle_trade_order({"side": "BUY", "quantity": 1, "timestamp": 0})
    Runner._handle_trade_order({"side": "SELL", "quantity": 1, "timestamp": 0})

    assert producer.messages == []
    Runner.set_activation_manager(None)
    Runner.set_trade_order_kafka_topic(None)
    Runner.set_kafka_producer(None)
