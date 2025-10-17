"""Basic StreamInput data provider.

This module provides a simple data ingestion layer using StreamInput.
"""

from __future__ import annotations

from qmtl.runtime.sdk import StreamInput


def create_data_stream(interval: str = "60s", period: int = 30) -> StreamInput:
    """Create a basic data stream.

    Args:
        interval: Data interval (e.g., "60s" for 1 minute)
        period: Number of periods to cache

    Returns:
        Configured StreamInput node
    """
    return StreamInput(
        interval=interval,
        period=period,
        name="price_stream",
    )


def get_data_provider():
    """Get the configured data provider.
    
    This is the main entry point for the data layer.
    Customize this function to use different data sources.
    """
    return create_data_stream()
