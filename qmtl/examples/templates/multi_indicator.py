r"""Multiple indicator strategy template.

Node flow:
    price -> fast_ema
          -> slow_ema
          -> rsi

ASCII DAG::

    [price]
      |\
      | \--->[slow_ema]
      |-->[fast_ema]
      \-->[rsi]
"""

import argparse
from qmtl.indicators import ema, rsi
from qmtl.sdk import Strategy, StreamInput, Runner


class MultiIndicatorStrategy(Strategy):
    """Combine several indicators from one input."""

    def setup(self):
        # Price stream feeding all downstream indicators
        price = StreamInput(interval="60s", period=50)
        # Short and long EMAs computed from the same source
        fast_ema = ema(price, period=5)
        slow_ema = ema(price, period=20)
        # Relative strength index from the same price history
        rsi_node = rsi(price, period=14)
        # Register all nodes so the DAG Manager can schedule them
        self.add_nodes([price, fast_ema, slow_ema, rsi_node])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--world-id")
    parser.add_argument("--gateway-url")
    args = parser.parse_args()

    if args.world_id and args.gateway_url:
        Runner.run(
            MultiIndicatorStrategy,
            world_id=args.world_id,
            gateway_url=args.gateway_url,
        )
    else:
        Runner.offline(MultiIndicatorStrategy)
