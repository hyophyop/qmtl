"""Portfolio update nodes."""

from __future__ import annotations

from typing import Any

from qmtl.runtime.sdk import metrics as sdk_metrics
from qmtl.runtime.sdk.node import CacheView, Node, ProcessingNode
from qmtl.runtime.sdk.portfolio import Portfolio

from ._shared import latest_entry, safe_call


class PortfolioNode(ProcessingNode):
    """Apply fills to a :class:`~qmtl.runtime.sdk.portfolio.Portfolio`."""

    def __init__(
        self,
        fills: Node,
        *,
        portfolio: Portfolio,
        name: str | None = None,
        watermark_topic: str | None = "trade.portfolio",
    ) -> None:
        self.fills = fills
        self.portfolio = portfolio
        self._watermark_topic = watermark_topic
        super().__init__(
            fills,
            compute_fn=self._compute,
            name=name or f"{fills.name}_portfolio",
            interval=fills.interval,
            period=1,
        )

    def _update_watermark(self, ts: int, fill: dict[str, Any]) -> None:
        if not self._watermark_topic:
            return
        try:
            from qmtl.runtime.sdk.watermark import set_watermark

            world = getattr(self.fills, "world_id", None) or "default"
            fill_ts = int(fill.get("timestamp", ts)) if isinstance(fill, dict) else int(ts)
            set_watermark(self._watermark_topic, world, fill_ts)
        except Exception:
            pass

    def _compute(self, view: CacheView) -> dict | None:
        latest = latest_entry(view, self.fills)
        if latest is None:
            return None
        ts, fill = latest
        safe_call(getattr(sdk_metrics, "record_fill_ingested", None))
        symbol = fill["symbol"]
        qty = float(fill["quantity"])
        price = float(fill.get("fill_price", fill.get("price", 0.0)))
        commission = float(fill.get("commission", 0.0))
        self.portfolio.apply_fill(symbol, qty, price, commission)
        self._update_watermark(ts, fill)
        snapshot = {
            "cash": self.portfolio.cash,
            "positions": {
                sym: {"qty": p.quantity, "price": p.market_price}
                for sym, p in self.portfolio.positions.items()
            },
        }
        return snapshot
