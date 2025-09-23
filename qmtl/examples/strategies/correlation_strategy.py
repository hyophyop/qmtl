from qmtl.sdk import Strategy, Node, TagQueryNode, Runner, MatchMode
import pandas as pd

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
            df = pd.concat(
                [pd.DataFrame([v for _, v in view[u][3600]]) for u in view],
                axis=1,
            )
            return df.corr(method="pearson")

        corr_node = Node(
            input=indicators,
            compute_fn=calc_corr,
            name="indicator_corr",
        )
        self.add_nodes([indicators, corr_node])


if __name__ == "__main__":
    # Running via Runner will automatically fetch matching queues and
    # subscribe to updates.
    Runner.run(CorrelationStrategy, world_id="correlation_demo", gateway_url="http://gateway.local")
