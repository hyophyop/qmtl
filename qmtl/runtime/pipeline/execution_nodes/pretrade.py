"""Pre-trade gating nodes."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from qmtl.runtime.brokerage import Account, BrokerageModel
from qmtl.runtime.sdk.node import CacheView, Node, ProcessingNode
from qmtl.runtime.sdk.order_gate import Activation
from qmtl.runtime.sdk.watermark import WatermarkGate, is_ready

from qmtl.runtime.transforms.execution_shared import run_pretrade_checks

from ._shared import latest_entry, normalise_watermark_gate, safe_call


class PreTradeGateNode(ProcessingNode):
    """Gate orders using ``check_pretrade`` from :mod:`qmtl.runtime.sdk.pretrade`."""

    def __init__(
        self,
        order: Node,
        *,
        activation_map: Mapping[str, Activation],
        brokerage: BrokerageModel,
        account: Account,
        backpressure_guard: Callable[[], bool] | None = None,
        require_portfolio_watermark: bool | WatermarkGate | Mapping[str, Any] | None = False,
        watermark_gate: WatermarkGate | Mapping[str, Any] | bool | None = None,
        name: str | None = None,
    ) -> None:
        self.order = order
        self.activation_map = activation_map
        self.brokerage = brokerage
        self.account = account
        self.backpressure_guard = backpressure_guard
        self.watermark_gate = normalise_watermark_gate(
            watermark_gate if watermark_gate is not None else require_portfolio_watermark
        )
        self.require_portfolio_watermark = self.watermark_gate.enabled
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_pretrade",
            interval=order.interval,
            period=1,
        )

    def _compute(self, view: CacheView[Mapping[str, Any]]) -> dict | None:
        latest = latest_entry(view, self.order)
        if latest is None:
            return None
        ts, order = latest
        if safe_call(self.backpressure_guard):
            return {"rejected": True, "reason": "backpressure"}
        if self.watermark_gate.enabled:
            try:
                interval = self.order.interval or 0
                if interval:
                    world = getattr(self.order, "world_id", None) or "default"
                    required = self.watermark_gate.required_timestamp(ts, interval)
                    if not is_ready(self.watermark_gate.topic, world, required):
                        return {"rejected": True, "reason": "watermark"}
            except Exception:
                pass

        _allowed, payload = run_pretrade_checks(
            order,
            activation_map=self.activation_map,
            brokerage=self.brokerage,
            account=self.account,
        )
        return payload
