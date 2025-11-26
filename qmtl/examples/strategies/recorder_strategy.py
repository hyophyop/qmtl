"""Recorder strategy example - QMTL v2.0."""

from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from qmtl.runtime.sdk import Runner, Strategy, Mode
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

        def momentum(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[price][60]])
            mom = df["close"].pct_change().rolling(5).mean()
            return pd.DataFrame({"momentum": mom})

        mom_node = Node(input=price, compute_fn=momentum, name="momentum")
        self.add_nodes([price, mom_node])


if __name__ == "__main__":
    metrics.start_metrics_server(port=8000)
    # v2 API: Submit with paper mode
    result = Runner.submit(RecorderStrategy, world="recorder_demo", mode=Mode.PAPER)
    print(f"Strategy submitted: {result.status}")
