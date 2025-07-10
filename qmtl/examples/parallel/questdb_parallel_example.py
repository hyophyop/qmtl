from __future__ import annotations

import asyncio
import pandas as pd

from qmtl.io import QuestDBRecorder
from qmtl.sdk import StreamInput, Node, Runner, metrics
from qmtl.examples.parallel_strategies_example import MA1 as BaseMA1, MA2 as BaseMA2


class MA1(BaseMA1):
    def setup(self) -> None:
        price = StreamInput(
            interval="60s",
            period=30,
            event_recorder=QuestDBRecorder(
                dsn="postgresql://localhost:8812/qdb",
            ),
        )

        def avg(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[price][60]])
            return pd.DataFrame({"ma_short": df["close"].rolling(5).mean()})

        ma_node = Node(input=price, compute_fn=avg, name="ma_short")
        self.add_nodes([price, ma_node])


class MA2(BaseMA2):
    def setup(self) -> None:
        price = StreamInput(
            interval="60s",
            period=60,
            event_recorder=QuestDBRecorder(
                dsn="postgresql://localhost:8812/qdb",
            ),
        )

        def avg(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[price][60]])
            return pd.DataFrame({"ma_long": df["close"].rolling(20).mean()})

        ma_node = Node(input=price, compute_fn=avg, name="ma_long")
        self.add_nodes([price, ma_node])


async def main() -> None:
    metrics.start_metrics_server(port=8000)
    task1 = asyncio.create_task(
        Runner.backtest_async(
            MA1,
            start_time=1700000000,
            end_time=1700003600,
            gateway_url="http://localhost:8000",
        )
    )
    task2 = asyncio.create_task(
        Runner.backtest_async(
            MA2,
            start_time=1700000000,
            end_time=1700003600,
            gateway_url="http://localhost:8000",
        )
    )
    await asyncio.gather(task1, task2)
    print(metrics.collect_metrics())


if __name__ == "__main__":
    asyncio.run(main())
