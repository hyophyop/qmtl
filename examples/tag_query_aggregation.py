from __future__ import annotations

import pandas as pd

from qmtl.sdk import Strategy, Node, TagQueryNode, Runner
from qmtl.io import QuestDBRecorder


class TagQueryAggregationStrategy(Strategy):
    """Compute correlation matrix from all ta-indicator streams."""

    def setup(self) -> None:
        indicators = TagQueryNode(
            query_tags=["ta-indicator"],
            interval="1h",
            period=24,
            match_mode="any",  # subscribe to any matching tag
        )
        # Runner takes care of queue resolution and subscriptions via TagQueryManager

        def calc_corr(view) -> pd.DataFrame:
            frames = [pd.DataFrame([v for _, v in view[u][3600]]) for u in view]
            if not frames:
                return pd.DataFrame()
            df = pd.concat(frames, axis=1)
            return df.corr(method="pearson")

        corr_node = Node(input=indicators, compute_fn=calc_corr, name="indicator_corr")
        # persist correlation matrices if a database is configured
        corr_node.event_recorder = QuestDBRecorder("postgresql://localhost:8812/qdb")

        self.add_nodes([indicators, corr_node])


if __name__ == "__main__":
    # Running in live mode automatically resolves queues and subscribes
    Runner.live(TagQueryAggregationStrategy)

