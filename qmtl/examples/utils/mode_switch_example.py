"""Mode switch example - QMTL v2.0.

Demonstrates how to run the same strategy across different modes.
"""

from __future__ import annotations

import argparse
import pandas as pd

from qmtl.runtime.sdk import Runner, Strategy, Mode
from qmtl.runtime.sdk.node import Node, StreamInput


class ModeSwitchStrategy(Strategy):
    """Run the same strategy across multiple execution modes."""

    def setup(self) -> None:
        price = StreamInput(interval="60s", period=30)

        def ma(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[price][60]])
            return pd.DataFrame({"ma": df["close"].rolling(5).mean()})

        ma_node = Node(input=price, compute_fn=ma, name="moving_avg")
        self.add_nodes([price, ma_node])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", "-w", help="Target world")
    parser.add_argument("--mode", "-m", choices=["backtest", "paper", "live"], default="backtest")
    args = parser.parse_args()

    # v2 API: Single entry point with mode
    result = Runner.submit(
        ModeSwitchStrategy,
        world=args.world,
        mode=Mode(args.mode),
    )
    print(f"Strategy submitted: {result.status}")
