"""Portfolio utilities for risk aggregation."""

from __future__ import annotations

from typing import Dict, Sequence, Tuple

from .models import PositionInfo


def aggregate_portfolios(
    portfolios: Sequence[Tuple[float, Dict[str, PositionInfo]]]
) -> Tuple[float, Dict[str, PositionInfo]]:
    """Aggregate positions across multiple strategies."""

    total_value = 0.0
    aggregated: Dict[str, PositionInfo] = {}

    for value, positions in portfolios:
        total_value += value
        for symbol, pos in positions.items():
            existing = aggregated.get(symbol)
            if existing:
                existing.quantity += pos.quantity
                existing.market_value += pos.market_value
                existing.unrealized_pnl += pos.unrealized_pnl
            else:
                aggregated[symbol] = PositionInfo(
                    symbol=symbol,
                    quantity=pos.quantity,
                    market_value=pos.market_value,
                    unrealized_pnl=pos.unrealized_pnl,
                    entry_price=pos.entry_price,
                    current_price=pos.current_price,
                )

    return total_value, aggregated


__all__ = ["aggregate_portfolios"]
