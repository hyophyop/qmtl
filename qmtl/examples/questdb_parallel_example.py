from __future__ import annotations

import asyncio

from qmtl.io import QuestDBRecorder
from qmtl.sdk import StreamInput, Runner, metrics
from qmtl.examples.parallel_strategies_example import MA1 as BaseMA1, MA2 as BaseMA2


class MA1(BaseMA1):
    def setup(self) -> None:
        super().setup()
        for node in self.nodes:
            if isinstance(node, StreamInput):
                node.event_recorder = QuestDBRecorder(
                    host="localhost",
                    port=8812,
                    database="qdb",
                )


class MA2(BaseMA2):
    def setup(self) -> None:
        super().setup()
        for node in self.nodes:
            if isinstance(node, StreamInput):
                node.event_recorder = QuestDBRecorder(
                    host="localhost",
                    port=8812,
                    database="qdb",
                )


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
