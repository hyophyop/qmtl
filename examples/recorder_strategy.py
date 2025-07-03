from __future__ import annotations

import pandas as pd

from qmtl.sdk import (
    Strategy,
    Node,
    StreamInput,
    Runner,
    metrics,
    QuestDBLoader,
    QuestDBRecorder,
)


class RecorderStrategy(Strategy):
    def setup(self) -> None:
        price = StreamInput(
            interval="60s",
            period=30,
            history_provider=QuestDBLoader("postgresql://localhost:8812/qdb"),
            event_recorder=QuestDBRecorder("postgresql://localhost:8812/qdb"),
        )

        def momentum(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[price][60]])
            mom = df["close"].pct_change().rolling(5).mean()
            return pd.DataFrame({"momentum": mom})

        mom_node = Node(input=price, compute_fn=momentum, name="momentum")
        self.add_nodes([price, mom_node])


if __name__ == "__main__":
    metrics.start_metrics_server(port=8000)
    Runner.dryrun(RecorderStrategy, gateway_url="http://localhost:8000")
