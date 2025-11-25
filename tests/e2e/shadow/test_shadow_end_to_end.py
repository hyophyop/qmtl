from __future__ import annotations

import asyncio
import time

import pytest

from qmtl.foundation.common.compute_key import ComputeContext as RunnerComputeContext, compute_compute_key
from qmtl.foundation.common.tagquery import MatchMode
from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.services import RunnerServices
from qmtl.runtime.transforms.publisher import TradeOrderPublisherNode
from qmtl.services.gateway.controlbus_consumer import ControlBusConsumer, ControlBusMessage
from qmtl.services.gateway.models import StrategySubmit
from qmtl.services.gateway.submission.context_service import ComputeContextService, StrategyComputeContext


class _StubWorldClient:
    def __init__(self, payload: dict | None):
        self._payload = payload or {}
        self.calls: list[str] = []

    async def get_decide(self, world_id: str):
        self.calls.append(world_id)
        return self._payload, False


class RecordingHub:
    """Minimal hub that captures queue/tag updates without networking."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self._started = asyncio.Event()

    async def start(self) -> None:
        self._started.set()

    async def stop(self) -> None:
        pass

    async def send_queue_update(
        self,
        tags,
        interval,
        queues,
        match_mode: MatchMode = MatchMode.ANY,
        *,
        world_id: str | None = None,
        execution_domain: str | None = None,
        etag: str | None = None,
        ts: str | None = None,
    ) -> None:
        self.events.append(
            (
                "queue_update",
                {
                    "tags": tags,
                    "interval": interval,
                    "queues": queues,
                    "match_mode": match_mode,
                    "world_id": world_id,
                    "execution_domain": execution_domain,
                    "etag": etag,
                    "ts": ts,
                    "version": 1,
                },
            )
        )

    async def send_tagquery_upsert(self, tags, interval, queues) -> None:
        self.events.append(
            (
                "tagquery.upsert",
                {"tags": tags, "interval": interval, "queues": queues, "version": 1},
            )
        )


class DummyService:
    def __init__(self) -> None:
        self.orders = []

    def post_order(self, order):
        self.orders.append(order)


def _make_submit(meta: dict | None = None) -> StrategySubmit:
    meta_payload = {"execution_domain": "shadow"}
    if meta:
        meta_payload.update(meta)
    return StrategySubmit(
        dag_json="{}",
        meta=meta_payload,
        world_ids=["shadow-world"],
        node_ids_crc32=0,
    )


@pytest.mark.asyncio
async def test_shadow_end_to_end_submission_queue_and_runner(monkeypatch) -> None:
    # Gateway: world decision returns shadow; context is preserved end-to-end.
    ws_client = _StubWorldClient({"effective_mode": "shadow"})
    ctx_service = ComputeContextService(world_client=ws_client)
    submit = _make_submit()

    strategy_ctx = await ctx_service.build(submit)

    assert isinstance(strategy_ctx, StrategyComputeContext)
    assert strategy_ctx.execution_domain == "shadow"
    assert strategy_ctx.safe_mode is False
    assert strategy_ctx.downgraded is False
    assert strategy_ctx.downgrade_reason is None
    assert strategy_ctx.context.world_id == "shadow-world"
    assert ws_client.calls == ["shadow-world"]

    # ControlBus -> WS hub: queue update carries world_id and execution_domain.
    hub = RecordingHub()
    consumer = ControlBusConsumer(
        brokers=[],
        topics=["queue"],
        group="shadow-test",
        ws_hub=hub,
    )
    await consumer.start()

    msg = ControlBusMessage(
        topic="queue",
        key="shadow:t",
        etag="e-shadow",
        run_id="r-shadow",
        data={
            "tags": ["shadow-tag"],
            "interval": 60,
            "queues": [{"queue": "q-shadow", "global": False}],
            "match_mode": "any",
            "world_id": strategy_ctx.context.world_id,
            "execution_domain": strategy_ctx.execution_domain,
            "ts": "2024-01-01T00:00:00Z",
            "etag": "e-shadow",
            "version": 1,
        },
        timestamp_ms=time.time() * 1000,
    )

    await consumer.publish(msg)
    await consumer._queue.join()
    await consumer.stop()

    queue_event = next(evt for evt in hub.events if evt[0] == "queue_update")[1]
    assert queue_event["world_id"] == "shadow-world"
    assert queue_event["execution_domain"] == "shadow"
    assert queue_event["match_mode"] == MatchMode.ANY
    # Ensure tagquery upsert is also emitted per (tags, interval, domain)
    tag_upsert = next(evt for evt in hub.events if evt[0] == "tagquery.upsert")[1]
    assert tag_upsert == {
        "tags": ["shadow-tag"],
        "interval": 60,
        "queues": [{"queue": "q-shadow", "global": False}],
        "version": 1,
    }

    # Runner: the same shadow context reaches the strategy; orders are gated off.
    from qmtl.runtime.sdk.runner import Runner

    original_services = Runner.services()
    original_trade_submission_enabled = Runner._enable_trade_submission
    Runner.set_services(RunnerServices.default())

    try:
        Runner.set_enable_trade_submission(True)
        trade_service = DummyService()
        Runner.set_trade_execution_service(trade_service)

        src = Node(name="sig", interval=1, period=1)
        pub = TradeOrderPublisherNode(src)
        runner_context = RunnerComputeContext(world_id="shadow-world", execution_domain="shadow")
        src.apply_compute_context(runner_context)
        pub.apply_compute_context(runner_context)

        result = Runner.feed_queue_data(
            pub,
            src.node_id,
            1,
            0,
            {"action": "BUY", "size": 1.0},
        )

        assert result is not None and result.get("side") == "BUY"
        assert trade_service.orders == []  # shadow domain blocks order dispatch
    finally:
        Runner.set_enable_trade_submission(original_trade_submission_enabled)
        Runner.set_services(original_services)

    active_context = pub.cache.active_context
    assert active_context is not None
    assert active_context.execution_domain == "shadow"

    shadow_key = compute_compute_key(pub.node_hash, runner_context)
    assert pub.compute_key == shadow_key
