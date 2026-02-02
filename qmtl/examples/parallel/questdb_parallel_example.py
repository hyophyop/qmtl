"""QuestDB parallel example - QMTL v2.0."""

from __future__ import annotations

import asyncio
import polars as pl

from qmtl.runtime.io import QuestDBRecorder
from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import Node, StreamInput
from qmtl.runtime.sdk.event_service import EventRecorderService
from qmtl.runtime.sdk import metrics
from qmtl.examples.parallel_strategies_example import MA1 as BaseMA1, MA2 as BaseMA2


class MA1(BaseMA1):
    def setup(self) -> None:
        price = StreamInput(
            interval="60s",
            period=30,
            event_service=EventRecorderService(
                QuestDBRecorder(
                    dsn="postgresql://localhost:8812/qdb",
                )
            ),
        )

        def avg(view) -> pl.DataFrame:
            df = pl.DataFrame([v for _, v in view[price][60]])
            ma_short = df.get_column("close").rolling_mean(window_size=5)
            return pl.DataFrame({"ma_short": ma_short})

        ma_node = Node(input=price, compute_fn=avg, name="ma_short")
        self.add_nodes([price, ma_node])


class MA2(BaseMA2):
    def setup(self) -> None:
        price = StreamInput(
            interval="60s",
            period=60,
            event_service=EventRecorderService(
                QuestDBRecorder(
                    dsn="postgresql://localhost:8812/qdb",
                )
            ),
        )

        def avg(view) -> pl.DataFrame:
            df = pl.DataFrame([v for _, v in view[price][60]])
            ma_long = df.get_column("close").rolling_mean(window_size=20)
            return pl.DataFrame({"ma_long": ma_long})

        ma_node = Node(input=price, compute_fn=avg, name="ma_long")
        self.add_nodes([price, ma_node])


async def main() -> None:
    metrics.start_metrics_server(port=8000)
    # v2 API: submit strategies; stage/mode is WorldService-governed
    result1 = Runner.submit(MA1)
    result2 = Runner.submit(MA2)
    print(f"MA1: {result1.status}, MA2: {result2.status}")
    print(metrics.collect_metrics())


if __name__ == "__main__":
    asyncio.run(main())
