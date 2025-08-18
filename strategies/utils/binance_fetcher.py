from __future__ import annotations

"""Asynchronous fetcher for Binance kline data."""

import time
from typing import Any

import httpx
import pandas as pd

from qmtl.sdk import DataFetcher


class BinanceFetcher(DataFetcher):
    """Fetch kline data from Binance REST API."""

    def __init__(self, symbol: str = "BTCUSDT", interval: str = "1m") -> None:
        self.symbol = symbol
        self.interval = interval
        self.base_url = "https://api.binance.com/api/v3/klines"

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        params = {
            "symbol": self.symbol,
            "interval": self.interval,
            "startTime": start * 1000,
            "endTime": end * 1000,
            "limit": 1000,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.base_url, params=params, timeout=10.0)
            resp.raise_for_status()
        data = resp.json()
        frame = pd.DataFrame(
            data,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base",
                "taker_buy_quote",
                "ignore",
            ],
        )
        frame["ts"] = (frame["close_time"].astype(int) // 1000)
        return frame[["ts", "open", "high", "low", "close", "volume"]]
