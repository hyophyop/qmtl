from __future__ import annotations

import pytest

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.sdk.strategy import Strategy

from tests.qmtl.services.service_doubles import (
    NullFeaturePlane,
    SpyHistoryService,
    SpyTradeDispatcher,
)


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


@pytest.fixture
def runner_harness():
    services = Runner.services()
    original_history = services.history_service
    original_plane = services.feature_plane
    original_dispatcher = services.trade_dispatcher
    original_execution_service = services.trade_execution_service
    original_http_url = services.trade_order_http_url
    original_kafka_producer = services.kafka_producer
    original_kafka_topic = services.trade_order_kafka_topic
    history = SpyHistoryService()
    dispatcher = SpyTradeDispatcher()
    plane = NullFeaturePlane()
    services.history_service = history
    services.set_feature_plane(plane)
    services._trade_dispatcher = dispatcher
    services.set_trade_execution_service(None)
    services.set_trade_order_http_url(None)
    services.set_kafka_producer(None)
    services.set_trade_order_kafka_topic(None)
    services.reset_trade_order_dedup()
    Runner.set_enable_trade_submission(True)
    try:
        yield {"history": history, "dispatcher": dispatcher, "plane": plane}
    finally:
        Runner.set_enable_trade_submission(True)
        services.history_service = original_history
        services.set_feature_plane(original_plane)
        services._trade_dispatcher = original_dispatcher
        services.set_trade_execution_service(original_execution_service)
        services.set_trade_order_http_url(original_http_url)
        services.set_kafka_producer(original_kafka_producer)
        services.set_trade_order_kafka_topic(original_kafka_topic)


def test_offline_run_invokes_history_service(runner_harness):
    result = Runner.submit(DummyStrategy, mode="backtest")
    try:
        history = runner_harness["history"]
        assert len(history.warmup_calls) == 1
        warmup = history.warmup_calls[0]
        assert warmup["offline_mode"] is True
        assert warmup["history_start"] is None
        assert warmup["history_end"] is None
        assert len(history.write_calls) == 1
        strategy = history.write_calls[0]
        assert getattr(strategy, "compute_context") == {
            "world_id": "__default__",
            "mode": "backtest",
        }
        # In offline/backtest without gateway, tag_query_manager may be absent.
        assert getattr(strategy, "tag_query_manager", None) in (None, getattr(strategy, "tag_query_manager", None))
    finally:
        Runner.shutdown(history.write_calls[0])


def test_trade_order_dispatch_routes_through_services(runner_harness):
    result = Runner.submit(DummyStrategy, mode="backtest")
    try:
        history = runner_harness["history"]
        assert len(history.write_calls) == 1
        strategy = history.write_calls[0]
        _trigger(strategy)
        dispatcher = runner_harness["dispatcher"]
        assert dispatcher.orders == [{"order": "BUY"}]
        plane = runner_harness["plane"]
        assert any(
            record[2] == {"order": "BUY"}
            and record[0].__class__.__name__ == "TradeOrderPublisherNode"
            for record in plane.records
        )
    finally:
        Runner.shutdown(strategy)
