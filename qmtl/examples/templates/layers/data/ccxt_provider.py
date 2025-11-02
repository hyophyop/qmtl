"""CCXT-based data provider.

This module integrates CCXT for exchange data retrieval.
"""

from __future__ import annotations

from qmtl.runtime.sdk import StreamInput
from qmtl.runtime.io import QuestDBHistoryProvider


def create_ccxt_stream(
    symbol: str = "BTC/USDT",
    interval: str = "60s",
    period: int = 30,
) -> StreamInput:
    """Create CCXT data stream.

    Args:
        symbol: Trading pair symbol
        interval: Data interval
        period: Number of periods to cache

    Returns:
        Configured StreamInput with CCXT data source
    """
    # Configure QuestDB as history provider
    history_provider = QuestDBHistoryProvider(
        dsn="postgresql://localhost:8812/qdb",
    )

    return StreamInput(
        interval=interval,
        period=period,
        name=f"{symbol.replace('/', '_')}_stream",
        history_provider=history_provider,
    )


def get_data_provider():
    """Get CCXT data provider."""
    return create_ccxt_stream()
