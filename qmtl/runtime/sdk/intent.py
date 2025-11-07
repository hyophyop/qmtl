from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional


@dataclass(frozen=True)
class PositionTarget:
    """Target position intent for a single symbol.

    One of ``target_percent`` or ``target_qty`` should be provided.
    ``target_percent`` is expressed as a fraction of the (strategy) portfolio
    total value. Positive for long exposure, negative for short (if supported).
    """

    symbol: str
    target_percent: float | None = None
    target_qty: float | None = None
    reason: str | None = None


def to_order_payloads(
    intents: Iterable[PositionTarget],
    *,
    price_by_symbol: Mapping[str, float] | None = None,
) -> List[dict]:
    """Convert position targets into order-intent dictionaries.

    This keeps the existing order-shaped payload contract so downstream sizing
    nodes can turn ``target_percent`` into concrete quantities using a
    :class:`~qmtl.runtime.sdk.portfolio.Portfolio` snapshot.
    """
    out: List[dict] = []
    for it in intents:
        payload: dict = {"symbol": it.symbol}
        if it.target_qty is not None:
            payload["quantity"] = float(it.target_qty)
        elif it.target_percent is not None:
            payload["target_percent"] = float(it.target_percent)
        if price_by_symbol and it.symbol in price_by_symbol:
            payload["price"] = float(price_by_symbol[it.symbol])
        if it.reason:
            payload["reason"] = it.reason
        out.append(payload)
    return out


__all__ = ["PositionTarget", "to_order_payloads"]

