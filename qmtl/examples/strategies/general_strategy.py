"""General strategy example - QMTL v2.0.

Demonstrates the simplified Runner.submit() API for strategy submission.
"""

import argparse
import polars as pl
from qmtl.runtime.io import QuestDBHistoryProvider, QuestDBRecorder
from qmtl.runtime.sdk import Runner, Strategy
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
            momentum = price_frame.frame.get_column("close").pct_change().rolling_mean(
                window_size=5
            )
            signal = (momentum > 0).cast(pl.Int64)
            return pl.DataFrame({"signal": signal})

        signal_node = Node(
            input=price_stream,
            compute_fn=generate_signal,
            name="momentum_signal",
        )
        self.add_nodes([price_stream, signal_node])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", "-w", help="Target world")
    args = parser.parse_args()

    # v2 API: single entry point; stage/mode is WorldService-governed
    result = Runner.submit(
        GeneralStrategy,
        world=args.world,
    )
    print(f"Strategy submitted: {result.status}")
