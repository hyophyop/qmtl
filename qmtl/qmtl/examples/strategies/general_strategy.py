import argparse
import pandas as pd

from qmtl.examples.defaults import load_backtest_defaults
from qmtl.io import QuestDBLoader, QuestDBRecorder
from qmtl.sdk import Strategy, Node, StreamInput, Runner

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest", action="store_true", help="Run backtest")
    parser.add_argument("--start-time")
    parser.add_argument("--end-time")
    parser.add_argument("--on-missing")
    args = parser.parse_args()

    defaults = load_backtest_defaults(__file__)
    start = args.start_time or defaults.get("start_time")
    end = args.end_time or defaults.get("end_time")
    on_missing = args.on_missing or defaults.get("on_missing", "skip")
    if args.backtest:
        Runner.backtest(
            GeneralStrategy,
            start_time=start,
            end_time=end,
            on_missing=on_missing,
        )
    else:
        Runner.offline(GeneralStrategy)
