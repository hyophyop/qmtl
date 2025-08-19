from __future__ import annotations

"""Asynchronous fetcher for Binance kline data."""

import asyncio
import atexit

import httpx
import pandas as pd

from qmtl.sdk.data_io import DataFetcher

_CLIENT: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return a persistent :class:`httpx.AsyncClient` instance."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient()
    return _CLIENT


async def _close_client() -> None:
    """Close the global :class:`httpx.AsyncClient` if open."""
    global _CLIENT
    if _CLIENT is not None:
        await _CLIENT.aclose()
        _CLIENT = None


def _close_client_sync() -> None:
    """Synchronously close the client at interpreter shutdown."""
    try:
        asyncio.run(_close_client())
    except RuntimeError:
        # Event loop already running; best-effort close
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_close_client())
        loop.close()


atexit.register(_close_client_sync)


class BinanceFetcher(DataFetcher):
    """Fetch kline data from Binance REST API."""

    base_url = "https://api.binance.com/api/v3/klines"

    def __init__(self, *, symbol: str | None = None, interval: str | None = None) -> None:
        self.symbol = symbol
        self.interval = interval

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await _close_client()

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: str
    ) -> pd.DataFrame:
        params = {
            "symbol": self.symbol or node_id,
            "interval": self.interval or interval,
            "startTime": start * 1000,
            "endTime": end * 1000,
            "limit": 1000,
        }
        client = _get_client()
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
        frame = frame.astype(
            {
                "open": float,
                "high": float,
                "low": float,
                "close": float,
                "volume": float,
            }
        )
        frame["ts"] = frame["close_time"].astype(int) // 1000
        return frame[["ts", "open", "high", "low", "close", "volume"]]
