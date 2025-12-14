r"""Branching strategy template - QMTL v2.0.

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
from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import Node, StreamInput
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
    parser.add_argument("--world", "-w", help="Target world")
    args = parser.parse_args()

    # v2 API: single entry point; stage/mode is WorldService-governed
    result = Runner.submit(
        BranchingStrategy,
        world=args.world,
    )
    print(f"Strategy submitted: {result.status}")
