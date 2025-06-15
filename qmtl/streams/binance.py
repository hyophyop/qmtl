"""Stream inputs for Binance data sources."""

from qmtl.sdk.node import StreamInput


class BinanceBTCStream(StreamInput):
    """Placeholder StreamInput for Binance BTC trades."""

    def __init__(self, *, interval: int, period: int) -> None:
        super().__init__(tags=["binance", "btc"], interval=interval, period=period)
