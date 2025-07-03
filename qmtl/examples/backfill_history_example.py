from __future__ import annotations

import asyncio
import httpx
import pandas as pd

from qmtl.sdk import Strategy, Node, StreamInput, Runner, DataFetcher
from qmtl.io import QuestDBLoader


class BinanceFetcher:
    """Simple DataFetcher for Binance kline history."""

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        url = (
            "https://api.binance.com/api/v3/klines"
            f"?symbol={node_id}&interval={interval}m"
            f"&startTime={start * 1000}&endTime={end * 1000}"
        )
        async with httpx.AsyncClient() as client:
            data = (await client.get(url)).json()
        rows = [
            {"ts": int(r[0] / 1000), "open": float(r[1]), "close": float(r[4])}
            for r in data
        ]
        return pd.DataFrame(rows)


fetcher = BinanceFetcher()
loader = QuestDBLoader("postgresql://localhost:8812/qdb", fetcher=fetcher)


class BackfillHistoryStrategy(Strategy):
    def setup(self) -> None:
        self.price = StreamInput(
            interval="1m",
            period=60,
            history_provider=loader,
        )

        def pct_change(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[self.price][60]])
            return pd.DataFrame({"ret": df["close"].pct_change()})

        ret_node = Node(input=self.price, compute_fn=pct_change, name="returns")
        self.add_nodes([self.price, ret_node])


async def main() -> None:
    start = 1700000000
    end = 1700003600

    strategy = Runner._prepare(BackfillHistoryStrategy)
    manager = Runner._init_tag_manager(strategy, None)
    Runner._apply_queue_map(strategy, {})
    await manager.resolve_tags(offline=True)
    await Runner._ensure_history(strategy, start, end)
    await Runner._replay_history(strategy, start, end)


if __name__ == "__main__":
    asyncio.run(main())
