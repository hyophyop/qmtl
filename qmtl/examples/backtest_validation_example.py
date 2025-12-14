"""Backtest validation example - QMTL v2.0.

Demonstrates the simplified Runner.submit() API.
"""

import argparse
from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import StreamInput


class ValidationStrategy(Strategy):
    """Minimal strategy containing a single price stream."""

    def setup(self):
        price = StreamInput(interval="60s", period=20)
        self.add_nodes([price])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", "-w", help="Target world")
    args = parser.parse_args()

    # v2 API: single entry point; stage/mode is WorldService-governed
    result = Runner.submit(
        ValidationStrategy,
        world=args.world,
    )
    print(f"Strategy submitted: {result.status}")


if __name__ == "__main__":
    main()
