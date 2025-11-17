from __future__ import annotations

import asyncio
import pandas as pd  # type: ignore[import-untyped]

from qmtl.runtime.sdk import (
    Node,
    Runner,
    Strategy,
    StreamInput,
    metrics,
)  # type: ignore[import-untyped]


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
    task1 = asyncio.create_task(Runner.offline_async(MA1))
    task2 = asyncio.create_task(Runner.offline_async(MA2))
    await asyncio.gather(task1, task2)
    print(metrics.collect_metrics())


if __name__ == "__main__":
    asyncio.run(main())
