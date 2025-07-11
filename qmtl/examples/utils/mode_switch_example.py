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
        "--mode", choices=["offline", "backtest", "dryrun", "live"], default="offline"
    )
    parser.add_argument("--gateway-url")
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    args = parser.parse_args()

    if args.mode == "backtest":
        Runner.backtest(
            ModeSwitchStrategy,
            start_time=args.start,
            end_time=args.end,
            gateway_url=args.gateway_url,
        )
    elif args.mode == "dryrun":
        Runner.dryrun(ModeSwitchStrategy, gateway_url=args.gateway_url)
    elif args.mode == "live":
        Runner.live(ModeSwitchStrategy, gateway_url=args.gateway_url)
    else:
        Runner.offline(ModeSwitchStrategy)
