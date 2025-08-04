r"""Single indicator strategy template.

Node flow:
    price -> ema

ASCII DAG::

    [price] -> [ema]
"""

import argparse

from qmtl.examples.defaults import load_backtest_defaults
from qmtl.indicators import ema
from qmtl.sdk import Strategy, StreamInput, Runner


class SingleIndicatorStrategy(Strategy):
    """Simple EMA example."""

    def setup(self):
        # Source price stream feeding the graph
        price = StreamInput(interval="60s", period=20)
        # Compute an exponential moving average from the price stream
        ema_node = ema(price, period=10)
        # Register nodes with the strategy in execution order
        self.add_nodes([price, ema_node])
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
            SingleIndicatorStrategy,
            start_time=start,
            end_time=end,
            on_missing=on_missing,
        )
    else:
        Runner.offline(SingleIndicatorStrategy)
