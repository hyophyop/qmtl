from qmtl.sdk import Strategy, Node, StreamInput, Runner
import pandas as pd

class CrossMarketLagStrategy(Strategy):
    def setup(self):
        btc_price = StreamInput(tags=["BTC", "price", "binance"], interval=60, period=120)
        mstr_price = StreamInput(tags=["MSTR", "price", "nasdaq"], interval=60, period=120)

        def lagged_corr(cache):
            btc = pd.DataFrame([v for _, v in cache[btc_price.node_id][60]])
            mstr = pd.DataFrame([v for _, v in cache[mstr_price.node_id][60]])
            btc_shift = btc["close"].shift(90)
            corr = btc_shift.corr(mstr["close"])
            return pd.DataFrame({"lag_corr": [corr]})

        corr_node = Node(
            input={"btc": btc_price, "mstr": mstr_price},
            compute_fn=lagged_corr,
            name="btc_mstr_corr",
        )

        self.add_nodes([btc_price, mstr_price, corr_node])

    def define_execution(self):
        self.set_target("btc_mstr_corr")


if __name__ == "__main__":
    Runner.dryrun(CrossMarketLagStrategy)
