"""Tag query strategy example - QMTL v2.0."""

from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]
from qmtl.runtime.sdk import Runner, Strategy, Mode
from qmtl.runtime.sdk.node import Node, TagQueryNode, MatchMode


class TagQueryStrategy(Strategy):
    """Example using TagQueryNode with multi-stage processing."""

    def setup(self):
        indicators = TagQueryNode(
            query_tags=["ta-indicator"],
            interval="1h",
            period=24,
            match_mode=MatchMode.ANY,  # default OR matching
        )
        # Runner creates TagQueryManager so the node receives queue mappings
        # and subscriptions automatically.

        def calc_corr(view) -> pd.DataFrame:
            aligned = view.align_frames([(node_id, 3600) for node_id in view], window=24)
            frames = [frame.frame for frame in aligned if not frame.frame.empty]
            if not frames:
                return pd.DataFrame()
            df = pd.concat(frames, axis=1)
            return df.corr(method="pearson")

        corr_node = Node(input=indicators, compute_fn=calc_corr, name="corr_matrix")

        def avg_corr(view) -> pd.DataFrame:
            latest = view.window(corr_node, 3600, 1)
            if not latest:
                return pd.DataFrame()
            _, corr_df = latest[-1]
            return pd.DataFrame({"avg_corr": [corr_df.mean().mean()]})

        avg_node = Node(input=corr_node, compute_fn=avg_corr, name="avg_corr")

        self.add_nodes([indicators, corr_node, avg_node])


if __name__ == "__main__":
    # v2 API: Submit with paper mode for real-time tag resolution
    result = Runner.submit(TagQueryStrategy, world="tag_query_demo", mode=Mode.PAPER)
    print(f"Strategy submitted: {result.status}")
