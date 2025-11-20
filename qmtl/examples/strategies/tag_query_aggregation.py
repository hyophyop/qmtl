from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from qmtl.runtime.sdk import EventRecorderService, MatchMode, Node, Runner, Strategy, TagQueryNode
from qmtl.runtime.io import QuestDBRecorder


class TagQueryAggregationStrategy(Strategy):
    """Compute correlation matrix from all ta-indicator streams."""

    def setup(self) -> None:
        indicators = TagQueryNode(
            query_tags=["ta-indicator"],
            interval="1h",
            period=24,
            match_mode=MatchMode.ANY,  # subscribe to any matching tag
        )
        # Runner takes care of queue resolution and subscriptions via TagQueryManager

        def calc_corr(view) -> pd.DataFrame:
            aligned = view.align_frames([(node_id, 3600) for node_id in view], window=24)
            frames = [frame.frame for frame in aligned if not frame.frame.empty]
            if not frames:
                return pd.DataFrame()
            df = pd.concat(frames, axis=1)
            return df.corr(method="pearson")

        corr_node = Node(
            input=indicators,
            compute_fn=calc_corr,
            name="indicator_corr",
            event_service=EventRecorderService(
                QuestDBRecorder(
                    dsn="postgresql://localhost:8812/qdb",
                )
            ),
        )

        self.add_nodes([indicators, corr_node])


if __name__ == "__main__":
    # Running under a world automatically resolves queues and subscribes
    Runner.run(TagQueryAggregationStrategy, world_id="tag_query_agg", gateway_url="http://gateway.local")
