"""Cross-market lag strategy example - QMTL v2.0."""

from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import Node, StreamInput
from qmtl.runtime.sdk.event_service import EventRecorderService
from qmtl.runtime.io import QuestDBHistoryProvider, QuestDBRecorder
import polars as pl

class CrossMarketLagStrategy(Strategy):
    def setup(self):
        btc_price = StreamInput(
            tags=["BTC", "price", "binance"],
            interval="60s",
            period=120,
            history_provider=QuestDBHistoryProvider(
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
            history_provider=QuestDBHistoryProvider(
                dsn="postgresql://localhost:8812/qdb",
            ),
            event_service=EventRecorderService(
                QuestDBRecorder(
                    dsn="postgresql://localhost:8812/qdb",
                )
            ),
        )
        def lagged_corr(view):
            btc = pl.DataFrame([v for _, v in view[btc_price][60]])
            mstr = pl.DataFrame([v for _, v in view[mstr_price][60]])
            btc_shift = btc.get_column("close").shift(90)
            corr = btc_shift.pearson_corr(mstr.get_column("close"))
            return pl.DataFrame({"lag_corr": [corr]})

        corr_node = Node(
            input=[btc_price, mstr_price],
            compute_fn=lagged_corr,
            name="btc_mstr_corr",
        )

        self.add_nodes([btc_price, mstr_price, corr_node])


if __name__ == "__main__":
    # v2 API: submit to WorldService; stage/mode is governed by world policy
    result = Runner.submit(CrossMarketLagStrategy, world="cross_market_lag")
    print(f"Strategy submitted: {result.status}")
