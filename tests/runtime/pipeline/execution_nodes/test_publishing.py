from __future__ import annotations

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.runner import Runner

from qmtl.runtime.pipeline.execution_nodes.publishing import OrderPublishNode


class DummyWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, list[tuple[str, str, dict, str | None]]]] = []

    async def publish_bucket(self, ts: int, interval: int, entries):
        self.calls.append((ts, interval, list(entries)))


class DummySubmit:
    def __init__(self) -> None:
        self.orders: list[dict] = []

    def __call__(self, order: dict) -> None:
        self.orders.append(order)


def test_order_publish_node_dispatches_payload() -> None:
    src = Node(name="src", interval=1, period=1)
    writer = DummyWriter()
    submit = DummySubmit()
    node = OrderPublishNode(src, commit_log_writer=writer, submit_order=submit)

    services = Runner.services()
    prev_manager = services.activation_manager
    Runner.set_activation_manager(None)
    try:
        order = {"symbol": "AAPL", "price": 10.0, "quantity": 1.0}
        out = Runner.feed_queue_data(node, src.node_id, 1, 0, order)
        assert out == order
        assert len(writer.calls) == 1
        assert submit.orders == [order]
    finally:
        Runner.set_activation_manager(prev_manager)
