from __future__ import annotations

import pytest

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.sdk.services import RunnerServices
from qmtl.runtime.sdk.strategy import Strategy
from qmtl.runtime.sdk.optional_services import RayExecutor

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
    previous = Runner.services()
    history = SpyHistoryService()
    dispatcher = SpyTradeDispatcher()
    plane = NullFeaturePlane()
    services = RunnerServices(
        history_service=history,
        trade_dispatcher=dispatcher,
        feature_plane=plane,
        ray_executor=RayExecutor(disabled=True),
    )
    Runner.set_services(services)
    Runner.set_enable_trade_submission(True)
    try:
        yield {"history": history, "dispatcher": dispatcher, "plane": plane}
    finally:
        Runner.set_enable_trade_submission(True)
        Runner.set_services(previous)


def test_offline_run_invokes_history_service(runner_harness):
    strategy = Runner.offline(DummyStrategy)
    try:
        history = runner_harness["history"]
        assert len(history.warmup_calls) == 1
        warmup = history.warmup_calls[0]
        assert warmup["offline_mode"] is True
        assert warmup["history_start"] is None
        assert warmup["history_end"] is None
        assert history.write_calls == [strategy]
        assert getattr(strategy, "compute_context") == {
            "world_id": "w",
            "execution_domain": "offline",
        }
        assert getattr(strategy, "tag_query_manager", None) is not None
    finally:
        Runner.shutdown(strategy)


def test_trade_order_dispatch_routes_through_services(runner_harness):
    strategy = Runner.offline(DummyStrategy)
    try:
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
