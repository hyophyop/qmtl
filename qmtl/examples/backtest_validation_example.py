"""Backtest validation example - QMTL v2.0.

Demonstrates the simplified Runner.submit() API.
"""

import argparse
from qmtl.runtime.sdk import Runner, Strategy, Mode
from qmtl.runtime.sdk.node import StreamInput


class ValidationStrategy(Strategy):
    """Minimal strategy containing a single price stream."""

    def setup(self):
        price = StreamInput(interval="60s", period=20)
        self.add_nodes([price])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", "-w", help="Target world")
    parser.add_argument("--mode", "-m", choices=["backtest", "paper", "live"], default="backtest")
    args = parser.parse_args()

    # v2 API: Single entry point
    result = Runner.submit(
        ValidationStrategy,
        world=args.world,
        mode=Mode(args.mode),
    )
    print(f"Strategy submitted: {result.status}")


if __name__ == "__main__":
    main()
