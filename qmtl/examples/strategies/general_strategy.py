from qmtl.sdk import Strategy, Node, StreamInput, Runner
from qmtl.io import QuestDBLoader, QuestDBRecorder
import pandas as pd

class GeneralStrategy(Strategy):
    def __init__(self):
        super().__init__(default_interval="60s", default_period=30)

    def setup(self):
        price_stream = StreamInput(
            history_provider=QuestDBLoader(
                dsn="postgresql://localhost:8812/qdb",
            ),
            event_recorder=QuestDBRecorder(
                dsn="postgresql://localhost:8812/qdb",
            ),
        )

        def generate_signal(view):
            price = pd.DataFrame([v for _, v in view[price_stream][60]])
            momentum = price["close"].pct_change().rolling(5).mean()
            signal = (momentum > 0).astype(int)
            return pd.DataFrame({"signal": signal})

        signal_node = Node(
            input=price_stream,
            compute_fn=generate_signal,
            name="momentum_signal",
        )
        self.add_nodes([price_stream, signal_node])


if __name__ == "__main__":
    # Enable Ray execution when available
    Runner.enable_ray()
    # The backfill range is provided via Runner.backtest
    Runner.backtest(
        GeneralStrategy,
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-02-01T00:00:00Z",
        on_missing="skip",
    )
