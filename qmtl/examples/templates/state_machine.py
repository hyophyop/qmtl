import argparse
import pandas as pd

from qmtl.examples.defaults import load_backtest_defaults
from qmtl.sdk import Strategy, StreamInput, Node, Runner


class StateMachineStrategy(Strategy):
    """Maintain a simple trend state between runs."""

    def setup(self):
        price = StreamInput(interval="60s", period=20)
        state = {"trend": None}

        def update_state(view):
            df = pd.DataFrame([v for _, v in view[price][60]])
            ema = df["close"].ewm(span=10).mean().iloc[-1]
            trend = "long" if df["close"].iloc[-1] > ema else "short"
            changed = trend != state.get("trend")
            state["trend"] = trend
            return pd.DataFrame({"trend": [trend], "changed": [changed]})

        trend_node = Node(input=price, compute_fn=update_state, name="trend_state")
        self.add_nodes([price, trend_node])


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
            StateMachineStrategy,
            start_time=start,
            end_time=end,
            on_missing=on_missing,
        )
    else:
        Runner.offline(StateMachineStrategy)
