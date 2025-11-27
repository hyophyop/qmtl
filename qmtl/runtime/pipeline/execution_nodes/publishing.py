"""Order publishing nodes."""

from __future__ import annotations

from typing import Any, Callable, Mapping, MutableMapping, cast

from qmtl.services.gateway.commit_log import CommitLogWriter
from qmtl.runtime.sdk import metrics as sdk_metrics
from qmtl.runtime.sdk.node import CacheView, Node, ProcessingNode

from qmtl.runtime.transforms.execution_nodes import activation_blocks_order

from ._shared import latest_entry, publish_commit_log, safe_call
from qmtl.runtime.pipeline.order_types import GatewayOrderPayload, prepare_gateway_payload


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

    def _compute(self, view: CacheView) -> GatewayOrderPayload | None:
        latest = latest_entry(view, self.order)
        if latest is None:
            return None
        ts, order = latest
        order_mapping = cast(Mapping[str, object], order)
        raw_payload: MutableMapping[str, object] = (
            order_mapping if isinstance(order_mapping, MutableMapping) else cast(MutableMapping[str, object], dict(order_mapping))
        )

        world_id = getattr(self.order, "world_id", None) or getattr(self, "world_id", None)
        strategy_id = getattr(self.order, "strategy_id", None) or getattr(self, "strategy_id", None)
        correlation_id = raw_payload.get("correlation_id")
        should_enrich = bool(self.commit_log_writer or self.submit_order)
        prepared: GatewayOrderPayload = prepare_gateway_payload(
            raw_payload,
            world_id=world_id,
            strategy_id=strategy_id,
            correlation_id=correlation_id if isinstance(correlation_id, str) else None,
            include_metadata=should_enrich,
        )
        mutable_payload: MutableMapping[str, object] = dict(prepared)
        if activation_blocks_order(mutable_payload):
            return prepared
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
            mutable_payload,
        )
        self._publish_gateway(mutable_payload)
        safe_call(getattr(sdk_metrics, "record_order_published", None))
        return prepared
