"""QuestDB parallel example - QMTL v2.0."""

from __future__ import annotations

import asyncio
import pandas as pd

from qmtl.runtime.io import QuestDBRecorder
from qmtl.runtime.sdk import Runner, Strategy, Mode
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
            event_service=EventRecorderService(
                QuestDBRecorder(
                    dsn="postgresql://localhost:8812/qdb",
                )
            ),
        )

        def avg(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[price][60]])
            return pd.DataFrame({"ma_long": df["close"].rolling(20).mean()})

        ma_node = Node(input=price, compute_fn=avg, name="ma_long")
        self.add_nodes([price, ma_node])


async def main() -> None:
    metrics.start_metrics_server(port=8000)
    # v2 API: Submit strategies with backtest mode
    result1 = Runner.submit(MA1, mode=Mode.BACKTEST)
    result2 = Runner.submit(MA2, mode=Mode.BACKTEST)
    print(f"MA1: {result1.status}, MA2: {result2.status}")
    print(metrics.collect_metrics())


if __name__ == "__main__":
    asyncio.run(main())
