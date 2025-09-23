from __future__ import annotations

import asyncio

from .node import StreamInput


class HistoryLoader:
    """Utility to load historical data for strategies."""

    @staticmethod
    async def load(strategy, start: int | None = None, end: int | None = None) -> None:
        if start is None or end is None:
            return
        tasks = [
            asyncio.create_task(n.load_history(start, end))
            for n in strategy.nodes
            if isinstance(n, StreamInput)
        ]
        if tasks:
            await asyncio.gather(*tasks)
