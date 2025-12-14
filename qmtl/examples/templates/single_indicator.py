r"""Single indicator strategy template - QMTL v2.0.

Node flow:
    price -> ema

ASCII DAG::

    [price] -> [ema]
"""

import argparse
from qmtl.runtime.indicators import ema
from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import StreamInput


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
    parser.add_argument("--world", "-w", help="Target world")
    args = parser.parse_args()

    # v2 API: single entry point; stage/mode is WorldService-governed
    result = Runner.submit(
        SingleIndicatorStrategy,
        world=args.world,
    )
    print(f"Strategy submitted: {result.status}")
