from __future__ import annotations

import argparse
import pandas as pd  # type: ignore[import-untyped]

from qmtl.runtime.sdk import Strategy, Node, StreamInput, Runner


class ModeSwitchStrategy(Strategy):
    """Run the same strategy across multiple execution domains."""

    def setup(self) -> None:
        price = StreamInput(interval="60s", period=30)

        def ma(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[price][60]])
            return pd.DataFrame({"ma": df["close"].rolling(5).mean()})

        ma_node = Node(input=price, compute_fn=ma, name="moving_avg")
        self.add_nodes([price, ma_node])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-url")
    parser.add_argument("--world-id")
    args = parser.parse_args()

    if args.world_id and args.gateway_url:
        Runner.run(
            ModeSwitchStrategy,
            world_id=args.world_id,
            gateway_url=args.gateway_url,
        )
    else:
        Runner.offline(ModeSwitchStrategy)
