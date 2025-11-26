r"""Multiple indicator strategy template - QMTL v2.0.

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
from qmtl.runtime.indicators import ema, rsi
from qmtl.runtime.sdk import Runner, Strategy, Mode
from qmtl.runtime.sdk.node import StreamInput


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
    parser.add_argument("--world", "-w", help="Target world")
    parser.add_argument("--mode", "-m", choices=["backtest", "paper", "live"], default="backtest")
    args = parser.parse_args()

    # v2 API: Single entry point
    result = Runner.submit(
        MultiIndicatorStrategy,
        world=args.world,
        mode=Mode(args.mode),
    )
    print(f"Strategy submitted: {result.status}")
