r"""State machine strategy template.

Node flow:
    price -> trend_state

ASCII DAG::

    [price] -> [trend_state]
"""

import argparse
import pandas as pd  # type: ignore[import-untyped]
from qmtl.runtime.sdk import Strategy, StreamInput, Node, Runner


class StateMachineStrategy(Strategy):
    """Maintain a simple trend state between runs."""

    def setup(self):
        # Price stream drives the state machine
        price = StreamInput(interval="60s", period=20)
        state = {"trend": None}

        def update_state(view):
            # Determine trend direction and emit whether it changed
            df = pd.DataFrame([v for _, v in view[price][60]])
            ema = df["close"].ewm(span=10).mean().iloc[-1]
            trend = "long" if df["close"].iloc[-1] > ema else "short"
            changed = trend != state.get("trend")
            state["trend"] = trend
            return pd.DataFrame({"trend": [trend], "changed": [changed]})

        trend_node = Node(input=price, compute_fn=update_state, name="trend_state")
        # Register nodes to form the DAG
        self.add_nodes([price, trend_node])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--world-id")
    parser.add_argument("--gateway-url")
    args = parser.parse_args()

    if args.world_id and args.gateway_url:
        Runner.run(
            StateMachineStrategy,
            world_id=args.world_id,
            gateway_url=args.gateway_url,
        )
    else:
        Runner.offline(StateMachineStrategy)
