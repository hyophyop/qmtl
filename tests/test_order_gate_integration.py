import importlib

import qmtl.runtime.sdk.runner as runner_module


class DummyActivationManager:
    def __init__(self, allow_long: bool = True, allow_short: bool = True) -> None:
        self.allow_long = allow_long
        self.allow_short = allow_short

    def allow_side(self, side: str) -> bool:
        s = side.lower()
        if s in {"buy", "long"}:
            return self.allow_long
        if s in {"sell", "short"}:
            return self.allow_short
        return False


class FakeKafkaProducer:
    def __init__(self) -> None:
        self.messages = []

    def send(self, topic, payload):
        self.messages.append((topic, payload))


def test_runner_gates_orders_by_activation():
    # Reload runner module to reset class-level state
    importlib.reload(runner_module)
    from qmtl.runtime.sdk.runner import Runner
    producer = FakeKafkaProducer()
    Runner.set_kafka_producer(producer)
    Runner.set_trade_order_kafka_topic("orders")

    # Disallow BUY/long; allow SELL/short
    Runner.set_activation_manager(DummyActivationManager(allow_long=False, allow_short=True))

    # BUY order should be dropped
    Runner._handle_trade_order({"side": "BUY", "quantity": 1, "timestamp": 0})
    # SELL order should be sent
    Runner._handle_trade_order({"side": "SELL", "quantity": 1, "timestamp": 0})

    assert producer.messages == [("orders", {"side": "SELL", "quantity": 1, "timestamp": 0})]

    Runner.set_activation_manager(None)
    Runner.set_trade_order_kafka_topic(None)
    Runner.set_kafka_producer(None)

