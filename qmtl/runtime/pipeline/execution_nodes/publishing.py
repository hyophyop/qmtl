"""Order publishing nodes."""

from __future__ import annotations

from typing import Any, Callable, Mapping, MutableMapping, cast

from qmtl.services.gateway.commit_log import CommitLogWriter
from qmtl.runtime.sdk import metrics as sdk_metrics
from qmtl.runtime.sdk.node import CacheView, Node, ProcessingNode

from qmtl.runtime.transforms.execution_nodes import activation_blocks_order

from ._shared import latest_entry, publish_commit_log, safe_call


class OrderPublishNode(ProcessingNode):
    """Publish orders to Gateway or commit log and pass them downstream."""

    def __init__(
        self,
        order: Node,
        *,
        commit_log_writer: CommitLogWriter | None = None,
        submit_order: Callable[[MutableMapping[str, object]], None] | None = None,
        name: str | None = None,
    ) -> None:
        self.order = order
        self.commit_log_writer = commit_log_writer
        self.submit_order = submit_order
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_publish",
            interval=order.interval,
            period=1,
        )

    def _publish_gateway(self, order: MutableMapping[str, object]) -> None:
        safe_call(self.submit_order, order)

    def _compute(self, view: CacheView) -> dict[str, Any] | None:
        latest = latest_entry(view, self.order)
        if latest is None:
            return None
        ts, order = latest
        if not isinstance(order, Mapping):
            return None
        order_payload: MutableMapping[str, object] = (
            order if isinstance(order, MutableMapping) else cast(MutableMapping[str, object], dict(order))
        )
        if activation_blocks_order(order_payload):
            return dict(order_payload)
        interval = self.order.interval
        if interval is None:
            return None
        try:
            interval_value = int(interval)
        except (TypeError, ValueError):
            return None
        publish_commit_log(
            self.commit_log_writer,
            self,
            self.order,
            ts,
            interval_value,
            order_payload,
        )
        self._publish_gateway(order_payload)
        safe_call(getattr(sdk_metrics, "record_order_published", None))
        return dict(order_payload)
