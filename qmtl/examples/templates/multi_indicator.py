import argparse

from qmtl.examples.defaults import load_backtest_defaults
from qmtl.indicators import ema, rsi
from qmtl.sdk import Strategy, StreamInput, Runner


class MultiIndicatorStrategy(Strategy):
    """Combine several indicators from one input."""

    def setup(self):
        price = StreamInput(interval="60s", period=50)
        fast_ema = ema(price, window=5)
        slow_ema = ema(price, window=20)
        rsi_node = rsi(price, window=14)
        self.add_nodes([price, fast_ema, slow_ema, rsi_node])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest", action="store_true", help="Run backtest")
    parser.add_argument("--start-time")
    parser.add_argument("--end-time")
    parser.add_argument("--on-missing")
    args = parser.parse_args()

    defaults = load_backtest_defaults(__file__)
    start = args.start_time or defaults.get("start_time")
    end = args.end_time or defaults.get("end_time")
    on_missing = args.on_missing or defaults.get("on_missing", "skip")

    if args.backtest:
        Runner.backtest(
            MultiIndicatorStrategy,
            start_time=start,
            end_time=end,
            on_missing=on_missing,
        )
    else:
        Runner.offline(MultiIndicatorStrategy)
