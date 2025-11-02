"""Example strategy demonstrating pre/post-market restrictions."""

from __future__ import annotations

from datetime import datetime, timezone

from qmtl.runtime.sdk import Strategy, StreamInput
from qmtl.runtime.sdk.timing_controls import TimingController, validate_backtest_timing


class TimingControlStrategy(Strategy):
    """Strategy that skips data outside regular market hours."""

    def __init__(self) -> None:
        super().__init__(default_interval="3600s", default_period=10)
        self.timing_controller = TimingController(allow_pre_post_market=False)

    def setup(self) -> None:
        price_stream = StreamInput(interval="3600s", period=10)
        self.add_nodes([price_stream])

    def validate_data(self):
        """Return timing validation issues for the loaded data."""
        return validate_backtest_timing(self, self.timing_controller)


if __name__ == "__main__":
    strategy = TimingControlStrategy()
    strategy.setup()

    # Add example data including a pre-market timestamp
    stream = strategy.nodes[0]
    pre_market_ts = int(datetime(2024, 1, 3, 8, 0, tzinfo=timezone.utc).timestamp() * 1000)
    stream.cache.append("prices", 3600, pre_market_ts, {"close": 100.0})

    issues = strategy.validate_data()
    print("Timing issues:", issues)
