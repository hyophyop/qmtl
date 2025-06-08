from qmtl.sdk import Strategy, Node, TagQueryNode, Runner
import pandas as pd

class CorrelationStrategy(Strategy):
    def setup(self):
        indicators = TagQueryNode(
            query_tags=["ta-indicator"],
            interval="1h",
            period=24,
        )

        def calc_corr(cache):
            df = pd.concat(
                [pd.DataFrame([v for _, v in cache[u][3600]]) for u in cache],
                axis=1,
            )
            return df.corr(method="pearson")

        corr_node = Node(
            input=indicators,
            compute_fn=calc_corr,
            name="indicator_corr",
        )
        self.add_nodes([indicators, corr_node])

    def define_execution(self):
        self.set_target("indicator_corr")


if __name__ == "__main__":
    Runner.live(CorrelationStrategy)
