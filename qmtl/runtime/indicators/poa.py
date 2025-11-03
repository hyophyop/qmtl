"""Price-over-arrival (POA) execution quality indicator."""

from __future__ import annotations

from typing import Literal

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

__all__ = ["poa"]


def _latest_price(view: CacheView, node: Node) -> float | None:
    """Return the latest numeric value emitted by ``node`` if available."""

    series = view[node][node.interval]
    latest = series.latest()
    if latest is None:
        return None

    _, value = latest
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def poa(
    fill_price: Node,
    arrival_price: Node,
    *,
    normalize: Literal["raw", "bps"] = "raw",
    name: str | None = None,
) -> Node:
    """Return a node computing fill slippage against the arrival price.

    Parameters
    ----------
    fill_price:
        Node emitting realized fill prices.
    arrival_price:
        Node emitting the reference arrival price used for execution.
    normalize:
        When ``"raw"`` (default) the relative slippage is expressed as a raw
        ratio (``fill / arrival - 1``). When ``"bps"`` the relative slippage is
        converted to basis points.
    name:
        Optional node name. Defaults to ``"poa"``.
    """

    def compute(view: CacheView) -> dict[str, float] | None:
        fill = _latest_price(view, fill_price)
        arrival = _latest_price(view, arrival_price)

        if fill is None or arrival is None or arrival == 0.0:
            return None

        abs_slippage = fill - arrival
        rel_slippage = abs_slippage / arrival

        if normalize == "bps":
            rel_slippage *= 10_000.0

        return {
            "abs_slippage": abs_slippage,
            "rel_slippage": rel_slippage,
        }

    period_candidates = [
        value
        for value in (fill_price.period, arrival_price.period)
        if isinstance(value, int)
    ]

    return Node(
        input=[fill_price, arrival_price],
        compute_fn=compute,
        name=name or "poa",
        interval=fill_price.interval,
        period=max(period_candidates, default=1),
    )
