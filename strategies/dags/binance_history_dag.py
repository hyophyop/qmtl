from __future__ import annotations

"""Strategy DAG that records Binance klines into QuestDB."""

from qmtl.sdk import Strategy, StreamInput, Node
from qmtl.io import QuestDBLoader, QuestDBRecorder

from strategies.utils.binance_fetcher import BinanceFetcher
from strategies.nodes.transforms.identity import identity_transform_node


class BinanceHistoryStrategy(Strategy):
    """Stream Binance prices and persist them using QuestDB."""

    def setup(self) -> None:
        fetcher = BinanceFetcher()
        price = StreamInput(
            tags=["BTCUSDT", "binance", "price"],
            interval="60s",
            period=120,
            history_provider=QuestDBLoader(
                dsn="postgresql://localhost:8812/qdb", fetcher=fetcher
            ),
            event_recorder=QuestDBRecorder(dsn="postgresql://localhost:8812/qdb"),
        )

        identity = Node(
            input=price,
            compute_fn=identity_transform_node,
            name="btc_identity",
            interval="60s",
            period=120,
        )
        self.add_nodes([price, identity])
