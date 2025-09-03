from qmtl.sdk import Strategy, Node, StreamInput, Runner, EventRecorderService
from qmtl.io import QuestDBLoader, QuestDBRecorder
import pandas as pd

class CrossMarketLagStrategy(Strategy):
    def setup(self):
        btc_price = StreamInput(
            tags=["BTC", "price", "binance"],
            interval="60s",
            period=120,
            history_provider=QuestDBLoader(
                dsn="postgresql://localhost:8812/qdb",
            ),
            event_service=EventRecorderService(
                QuestDBRecorder(
                    dsn="postgresql://localhost:8812/qdb",
                )
            ),
        )
        mstr_price = StreamInput(
            tags=["MSTR", "price", "nasdaq"],
            interval="60s",
            period=120,
            history_provider=QuestDBLoader(
                dsn="postgresql://localhost:8812/qdb",
            ),
            event_service=EventRecorderService(
                QuestDBRecorder(
                    dsn="postgresql://localhost:8812/qdb",
                )
            ),
        )
        def lagged_corr(view):
            btc = pd.DataFrame([v for _, v in view[btc_price][60]])
            mstr = pd.DataFrame([v for _, v in view[mstr_price][60]])
            btc_shift = btc["close"].shift(90)
            corr = btc_shift.corr(mstr["close"])
            return pd.DataFrame({"lag_corr": [corr]})

        corr_node = Node(
            input=[btc_price, mstr_price],
            compute_fn=lagged_corr,
            name="btc_mstr_corr",
        )

        self.add_nodes([btc_price, mstr_price, corr_node])


if __name__ == "__main__":
    Runner.run(CrossMarketLagStrategy, world_id="cross_market_lag", gateway_url="http://gateway.local")
