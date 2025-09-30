r"""Single indicator strategy template.

Node flow:
    price -> ema

ASCII DAG::

    [price] -> [ema]
"""

import argparse
from qmtl.runtime.indicators import ema
from qmtl.runtime.sdk import Strategy, StreamInput, Runner


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
    parser.add_argument("--world-id")
    parser.add_argument("--gateway-url")
    args = parser.parse_args()

    if args.world_id and args.gateway_url:
        Runner.run(
            SingleIndicatorStrategy,
            world_id=args.world_id,
            gateway_url=args.gateway_url,
        )
    else:
        Runner.offline(SingleIndicatorStrategy)
