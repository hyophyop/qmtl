r"""Branching strategy template.

Node flow:
    price -> momentum
          -> volatility

ASCII DAG::

    [price]
      |\
      | \-->[volatility]
      \-->[momentum]
"""

from pathlib import Path
import argparse

from qmtl.examples.defaults import load_backtest_defaults
from qmtl.sdk import Strategy, StreamInput, Node, Runner
import pandas as pd


class BranchingStrategy(Strategy):
    """Demonstrate branching computations from one source."""

    def setup(self):
        # Base price stream shared by all downstream nodes
        price = StreamInput(interval="60s", period=30)

        def calc_momentum(view):
            # Momentum computed from recent price history
            df = pd.DataFrame([v for _, v in view[price][60]])
            return pd.DataFrame({"momentum": df["close"].pct_change()})

        def calc_volatility(view):
            # Volatility branch calculating rolling standard deviation
            df = pd.DataFrame([v for _, v in view[price][60]])
            vol = df["close"].pct_change().rolling(10).std()
            return pd.DataFrame({"volatility": vol})

        momentum = Node(input=price, compute_fn=calc_momentum, name="momentum")
        volatility = Node(input=price, compute_fn=calc_volatility, name="volatility")
        # Register all nodes to build the DAG
        self.add_nodes([price, momentum, volatility])


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
            BranchingStrategy,
            start_time=start,
            end_time=end,
            on_missing=on_missing,
        )
    else:
        Runner.offline(BranchingStrategy)
