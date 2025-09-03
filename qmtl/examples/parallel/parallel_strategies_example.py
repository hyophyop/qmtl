from __future__ import annotations

import asyncio
import pandas as pd

from qmtl.sdk import Strategy, Node, StreamInput, Runner, metrics


class MA1(Strategy):
    def setup(self) -> None:
        price = StreamInput(interval="60s", period=30)

        def avg(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[price][60]])
            return pd.DataFrame({"ma_short": df["close"].rolling(5).mean()})

        ma_node = Node(input=price, compute_fn=avg, name="ma_short")
        self.add_nodes([price, ma_node])


class MA2(Strategy):
    def setup(self) -> None:
        price = StreamInput(interval="60s", period=60)

        def avg(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[price][60]])
            return pd.DataFrame({"ma_long": df["close"].rolling(20).mean()})

        ma_node = Node(input=price, compute_fn=avg, name="ma_long")
        self.add_nodes([price, ma_node])


async def main() -> None:
    metrics.start_metrics_server(port=8000)
    task1 = asyncio.create_task(
        Runner.run_async(
            MA1,
            world_id="parallel_ma1",
            gateway_url="http://localhost:8000",
            offline=True,
        )
    )
    task2 = asyncio.create_task(
        Runner.run_async(
            MA2,
            world_id="parallel_ma2",
            gateway_url="http://localhost:8000",
            offline=True,
        )
    )
    await asyncio.gather(task1, task2)
    print(metrics.collect_metrics())


if __name__ == "__main__":
    asyncio.run(main())
