from __future__ import annotations

import argparse
import pandas as pd

from qmtl.sdk import Strategy, Node, StreamInput, Runner


class ModeSwitchStrategy(Strategy):
    """Run the same strategy in multiple modes."""

    def setup(self) -> None:
        price = StreamInput(interval="60s", period=30)

        def ma(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[price][60]])
            return pd.DataFrame({"ma": df["close"].rolling(5).mean()})

        ma_node = Node(input=price, compute_fn=ma, name="moving_avg")
        self.add_nodes([price, ma_node])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["offline", "run"], default="offline"
    )
    parser.add_argument("--gateway-url")
    parser.add_argument("--world-id", default="mode_switch_example")
    args = parser.parse_args()

    if args.mode == "run":
        Runner.run(
            ModeSwitchStrategy,
            world_id=args.world_id,
            gateway_url=args.gateway_url,
        )
    else:
        Runner.offline(ModeSwitchStrategy)
