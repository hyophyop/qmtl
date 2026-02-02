"""Recorder strategy example - QMTL v2.0."""

from __future__ import annotations

import polars as pl

from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import Node, StreamInput
from qmtl.runtime.sdk.event_service import EventRecorderService
from qmtl.runtime.sdk import metrics
from qmtl.runtime.io import QuestDBHistoryProvider, QuestDBRecorder


class RecorderStrategy(Strategy):
    def setup(self) -> None:
        price = StreamInput(
            interval="60s",
            period=30,
            history_provider=QuestDBHistoryProvider("postgresql://localhost:8812/qdb"),
            event_service=EventRecorderService(QuestDBRecorder("postgresql://localhost:8812/qdb")),
        )

        def momentum(view) -> pl.DataFrame:
            df = pl.DataFrame([v for _, v in view[price][60]])
            close = df.get_column("close")
            mom = close.pct_change().rolling_mean(window_size=5)
            return pl.DataFrame({"momentum": mom})

        mom_node = Node(input=price, compute_fn=momentum, name="momentum")
        self.add_nodes([price, mom_node])


if __name__ == "__main__":
    metrics.start_metrics_server(port=8000)
    # v2 API: submit to WorldService; stage/mode is governed by world policy
    result = Runner.submit(RecorderStrategy, world="recorder_demo")
    print(f"Strategy submitted: {result.status}")
