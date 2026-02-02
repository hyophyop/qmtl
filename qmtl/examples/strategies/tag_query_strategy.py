"""Tag query strategy example - QMTL v2.0."""

from __future__ import annotations

from typing import cast

import polars as pl
from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import MatchMode, Node, TagQueryNode


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

        def calc_corr(view) -> pl.DataFrame:
            aligned = view.align_frames([(node_id, 3600) for node_id in view], window=24)
            frames = [
                cast(pl.DataFrame, frame.frame) for frame in aligned if not frame.frame.is_empty()
            ]
            if not frames:
                return pl.DataFrame()
            df = pl.concat(frames, how="horizontal")
            return df.corr()

        corr_node = Node(input=indicators, compute_fn=calc_corr, name="corr_matrix")

        def avg_corr(view) -> pl.DataFrame:
            latest = view.window(corr_node, 3600, 1)
            if not latest:
                return pl.DataFrame()
            _, corr_df = latest[-1]
            corr_frame = cast(pl.DataFrame, corr_df)
            col_means = corr_frame.select(pl.all().mean()).row(0)
            avg_corr_value = sum(col_means) / len(col_means) if col_means else None
            return pl.DataFrame({"avg_corr": [avg_corr_value]})

        avg_node = Node(input=corr_node, compute_fn=avg_corr, name="avg_corr")

        self.add_nodes([indicators, corr_node, avg_node])


if __name__ == "__main__":
    # v2 API: submit to WorldService; stage/mode is governed by world policy
    result = Runner.submit(TagQueryStrategy, world="tag_query_demo")
    print(f"Strategy submitted: {result.status}")
