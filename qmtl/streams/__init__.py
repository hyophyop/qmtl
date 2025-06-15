"""StreamInput implementations for common data sources.

Each class keeps a narrow focus and does not depend on other namespaces.
New streams must be accompanied by tests under ``tests/``.
"""

from qmtl.sdk.node import StreamInput


class BinanceBTCStream(StreamInput):
    """Placeholder StreamInput for Binance BTC trades."""

    def __init__(self, *, interval: int, period: int) -> None:
        super().__init__(tags=["binance", "btc"], interval=interval, period=period)

