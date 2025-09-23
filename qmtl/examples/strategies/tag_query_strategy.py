from __future__ import annotations

from qmtl.runtime.sdk import Strategy, Node, TagQueryNode, Runner, MatchMode
import pandas as pd


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
            frames = [pd.DataFrame([v for _, v in view[u][3600]]) for u in view]
            if not frames:
                return pd.DataFrame()
            df = pd.concat(frames, axis=1)
            return df.corr(method="pearson")

        corr_node = Node(input=indicators, compute_fn=calc_corr, name="corr_matrix")

        def avg_corr(view) -> pd.DataFrame:
            latest = view[corr_node][3600].latest()
            if latest is None:
                return pd.DataFrame()
            _, corr_df = latest
            return pd.DataFrame({"avg_corr": [corr_df.mean().mean()]})

        avg_node = Node(input=corr_node, compute_fn=avg_corr, name="avg_corr")

        self.add_nodes([indicators, corr_node, avg_node])


if __name__ == "__main__":
    # Running the strategy triggers automatic tag resolution and
    # WebSocket subscriptions under the selected world.
    Runner.run(TagQueryStrategy, world_id="tag_query_demo", gateway_url="http://gateway.local")
