"""Correlation strategy example - QMTL v2.0."""

import polars as pl
from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import Node, TagQueryNode, MatchMode

class CorrelationStrategy(Strategy):
    def setup(self):
        indicators = TagQueryNode(
            query_tags=["ta-indicator"],
            interval="1h",
            period=24,
            match_mode=MatchMode.ANY,  # default OR matching
        )
        # Queue resolution and subscription are handled automatically by Runner
        # through TagQueryManager.

        def calc_corr(view):
            aligned = view.align_frames([(node_id, 3600) for node_id in view], window=24)
            frames = [frame.frame for frame in aligned if not frame.frame.is_empty()]
            if not frames:
                return pl.DataFrame()
            df = pl.concat(frames, how="horizontal")
            return df.corr()

        corr_node = Node(
            input=indicators,
            compute_fn=calc_corr,
            name="indicator_corr",
        )
        self.add_nodes([indicators, corr_node])


if __name__ == "__main__":
    # v2 API: submit to WorldService; stage/mode is governed by world policy
    result = Runner.submit(CorrelationStrategy, world="correlation_demo")
    print(f"Strategy submitted: {result.status}")
