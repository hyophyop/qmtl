from qmtl.sdk import Strategy, StreamInput, Node, Runner
import pandas as pd


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
    Runner.offline(StateMachineStrategy)
