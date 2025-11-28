"""Multi-asset lag strategy example - QMTL v2.0."""

from qmtl.runtime.sdk import Runner, Strategy, Mode
from qmtl.runtime.sdk.node import Node, StreamInput
from qmtl.runtime.sdk.event_service import EventRecorderService
from qmtl.runtime.io import QuestDBHistoryProvider, QuestDBRecorder
import pandas as pd

class MultiAssetLagStrategy(Strategy):
    def setup(self):
        btc_price = StreamInput(
            tags=["BTC", "price", "binance"],
            interval="60s",
            period=120,
            history_provider=QuestDBHistoryProvider("postgresql://localhost:8812/qdb"),
            event_service=EventRecorderService(QuestDBRecorder("postgresql://localhost:8812/qdb")),
        )
        mstr_price = StreamInput(
            tags=["MSTR", "price", "nasdaq"],
            interval="60s",
            period=120,
            history_provider=QuestDBHistoryProvider("postgresql://localhost:8812/qdb"),
            event_service=EventRecorderService(QuestDBRecorder("postgresql://localhost:8812/qdb")),
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
    # v2 API: Submit with paper mode
    result = Runner.submit(
        MultiAssetLagStrategy,
        world="multi_asset_lag",
        mode=Mode.PAPER,
    )
    print(f"Strategy submitted: {result.status}")
