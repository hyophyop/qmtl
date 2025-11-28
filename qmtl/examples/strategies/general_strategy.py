"""General strategy example - QMTL v2.0.

Demonstrates the simplified Runner.submit() API for strategy submission.
"""

import argparse
import pandas as pd
from qmtl.runtime.io import QuestDBHistoryProvider, QuestDBRecorder
from qmtl.runtime.sdk import Runner, Strategy, Mode
from qmtl.runtime.sdk.node import Node, StreamInput
from qmtl.runtime.sdk.event_service import EventRecorderService

class GeneralStrategy(Strategy):
    def __init__(self):
        super().__init__(default_interval="60s", default_period=30)

    def setup(self):
        price_stream = StreamInput(
            history_provider=QuestDBHistoryProvider(
                dsn="postgresql://localhost:8812/qdb",
            ),
            event_service=EventRecorderService(
                QuestDBRecorder(
                    dsn="postgresql://localhost:8812/qdb",
                )
            ),
        )

        def generate_signal(view):
            price_frame = view.as_frame(price_stream, 60, columns=["close"]).validate_columns(
                ["close"]
            )
            momentum = price_frame.frame["close"].pct_change().rolling(5).mean()
            signal = (momentum > 0).astype(int)
            return pd.DataFrame({"signal": signal})

        signal_node = Node(
            input=price_stream,
            compute_fn=generate_signal,
            name="momentum_signal",
        )
        self.add_nodes([price_stream, signal_node])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", "-w", help="Target world")
    parser.add_argument("--mode", "-m", choices=["backtest", "paper", "live"], default="backtest")
    args = parser.parse_args()

    # v2 API: Single entry point for all execution modes
    result = Runner.submit(
        GeneralStrategy,
        world=args.world,
        mode=Mode(args.mode),
    )
    print(f"Strategy submitted: {result.status}")
