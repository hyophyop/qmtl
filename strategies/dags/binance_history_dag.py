from __future__ import annotations

"""Strategy DAG that records Binance klines into QuestDB."""

from qmtl.sdk import Strategy, StreamInput, Node
from qmtl.io import QuestDBLoader, QuestDBRecorder

from strategies.config import load_config
from strategies.utils.binance_fetcher import BinanceFetcher
from strategies.nodes.transforms.identity import identity_transform_node


class BinanceHistoryStrategy(Strategy):
    """Stream Binance prices and persist them using QuestDB."""

    def setup(self) -> None:
        cfg = load_config()
        questdb_dsn = cfg.get("questdb_dsn")
        streams = cfg.get("streams", [])

        fetcher = BinanceFetcher()
        nodes: list[Node] = []

        for stream in streams:
            symbol = stream.get("symbol")
            interval = stream.get("interval", "60s")

            price = StreamInput(
                tags=[symbol, "binance", "price"],
                interval=interval,
                period=120,
                history_provider=QuestDBLoader(dsn=questdb_dsn, fetcher=fetcher),
                event_recorder=QuestDBRecorder(dsn=questdb_dsn),
            )

            identity = Node(
                input=price,
                compute_fn=identity_transform_node,
                name=f"{symbol.lower()}_identity",
                interval=interval,
                period=120,
            )

            nodes.extend([price, identity])

        self.add_nodes(nodes)
