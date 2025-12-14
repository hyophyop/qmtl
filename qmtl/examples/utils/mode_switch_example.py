"""Submission example - QMTL v2.0.

QMTL v2 exposes a single submission surface: ``Runner.submit(strategy, world=...)``.
Execution stage (backtest/paper/live) is governed by WorldService policy, not a
client-side mode flag.
"""

from __future__ import annotations

import argparse
import pandas as pd

from qmtl.runtime.sdk import Runner, Strategy
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
    args = parser.parse_args()

    # v2 API: single entry point; stage/mode is WorldService-governed
    result = Runner.submit(
        ModeSwitchStrategy,
        world=args.world,
    )
    print(f"Strategy submitted: {result.status}")
