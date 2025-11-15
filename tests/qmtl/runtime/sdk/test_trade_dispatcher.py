from __future__ import annotations

import pytest
from cachetools import TTLCache

from qmtl.runtime.sdk.trade_dispatcher import TradeOrderDispatcher
from qmtl.runtime.sdk.dispatch_pipeline import (
    DispatchContext,
    HttpSubmitStep,
    KafkaSubmitStep,
)


class RecordingPoster:
    calls: list[tuple[str, dict]] = []

    @classmethod
    def post(cls, url: str, json: dict) -> None:
        cls.calls.append((url, json))


class RecordingProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    def send(self, topic: str, payload: dict) -> None:
        self.sent.append((topic, payload))


class RecordingService:
    def __init__(self) -> None:
        self.orders: list[dict] = []

    def post_order(self, order: dict) -> None:
        self.orders.append(order)


class DenyActivation:
    def allow_side(self, side: str) -> bool:
        return False


@pytest.fixture(autouse=True)
def clear_poster_calls() -> None:
    RecordingPoster.calls.clear()
    yield
    RecordingPoster.calls.clear()


def test_dispatcher_gates_via_activation_manager() -> None:
    dispatcher = TradeOrderDispatcher(
        http_poster=RecordingPoster,
        dedup_cache=TTLCache(maxsize=10, ttl=60),
        activation_manager=DenyActivation(),
        trade_order_http_url="http://endpoint",
    )

    dispatcher.dispatch({"side": "BUY", "quantity": 1, "timestamp": 0})

    assert RecordingPoster.calls == []


def test_dispatcher_deduplicates_orders() -> None:
    dispatcher = TradeOrderDispatcher(
        http_poster=RecordingPoster,
        dedup_cache=TTLCache(maxsize=10, ttl=60),
        trade_order_http_url="http://endpoint",
    )

    order = {"side": "SELL", "quantity": 1, "timestamp": 1}
    dispatcher.dispatch(order)
    dispatcher.dispatch(order)

    assert len(RecordingPoster.calls) == 1


def test_dispatcher_uses_http_and_kafka() -> None:
    producer = RecordingProducer()
    dispatcher = TradeOrderDispatcher(
        http_poster=RecordingPoster,
        dedup_cache=TTLCache(maxsize=10, ttl=60),
        trade_order_http_url="http://endpoint",
        kafka_producer=producer,
        trade_order_kafka_topic="orders",
    )

    order = {"side": "BUY", "quantity": 2, "timestamp": 2}
    dispatcher.dispatch(order)

    assert RecordingPoster.calls == [("http://endpoint", order)]
    assert producer.sent == [("orders", order)]


def test_trade_execution_service_takes_precedence() -> None:
    service = RecordingService()
    dispatcher = TradeOrderDispatcher(
        http_poster=RecordingPoster,
        dedup_cache=TTLCache(maxsize=10, ttl=60),
        trade_execution_service=service,
        trade_order_http_url="http://endpoint",
    )

    order = {"side": "BUY", "quantity": 3, "timestamp": 3}
    dispatcher.dispatch(order)

    assert service.orders == [order]
    assert RecordingPoster.calls == []


def test_payload_validation_blocks_invalid_orders() -> None:
    dispatcher = TradeOrderDispatcher(
        http_poster=RecordingPoster,
        dedup_cache=TTLCache(maxsize=10, ttl=60),
        trade_order_http_url="http://endpoint",
    )

    dispatcher.dispatch("not-an-order")

    assert RecordingPoster.calls == []


def test_http_submit_step_logs_final_failure(caplog: pytest.LogCaptureFixture) -> None:
    class AlwaysFailPoster:
        calls = 0

        @classmethod
        def post(cls, url: str, json: dict) -> None:
            cls.calls += 1
            raise RuntimeError("boom")

    step = HttpSubmitStep(AlwaysFailPoster, "http://endpoint")
    context = DispatchContext({"side": "BUY"})

    with caplog.at_level("WARNING"):
        step.handle(context)

    assert AlwaysFailPoster.calls == 2
    assert "trade order HTTP submit failed; dropping order" in caplog.text


def test_kafka_submit_step_logs_and_raises(caplog: pytest.LogCaptureFixture) -> None:
    class FailingProducer:
        def send(self, topic: str, payload: dict) -> None:
            raise RuntimeError("kafka down")

    producer = FailingProducer()
    step = KafkaSubmitStep(producer, "orders")
    context = DispatchContext({"side": "BUY"})

    with caplog.at_level("WARNING"):
        with pytest.raises(RuntimeError):
            step.handle(context)

    assert "trade order Kafka submit failed; raising for caller handling" in caplog.text
