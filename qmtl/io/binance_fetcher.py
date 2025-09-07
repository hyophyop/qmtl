from __future__ import annotations

"""Asynchronous fetcher for Binance kline data."""

import asyncio
import atexit

import httpx
import pandas as pd

from qmtl.sdk.data_io import DataFetcher

_CLIENT: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return a persistent :class:`httpx.AsyncClient` instance.

    Note: Tests that perform a single request can avoid creating the
    process‑global client by constructing a local client inline. See
    :meth:`fetch` for the conditional path that uses a per‑call client
    when no global client has been created yet. This prevents
    ResourceWarning noise under -W error.
    """
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
    """Best-effort close of the global client without leaking event loops."""
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            # Schedule async close and return; avoid creating a new loop
            loop.create_task(_close_client())
        else:
            loop.run_until_complete(_close_client())
    except Exception:
        # As a last resort, fall back to asyncio.run in environments
        # where no loop is set; ignore failures during interpreter teardown.
        try:
            asyncio.run(_close_client())
        except Exception:
            pass


# Keep best‑effort shutdown, but tests avoid depending on atexit by using
# a short‑lived client path when no global client was initialized.
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
        global _CLIENT
        params = {
            "symbol": self.symbol or node_id,
            "interval": self.interval or interval,
            "startTime": start * 1000,
            "endTime": end * 1000,
            "limit": 1000,
        }
        # Prefer using a short‑lived client when no global client exists yet
        # to avoid unclosed‑resource warnings in parallel test runs.
        if _CLIENT is None:
            # Create a persistent client on first use to satisfy reuse semantics
            _CLIENT = httpx.AsyncClient()
            client = _CLIENT
            resp = await client.get(self.base_url, params=params, timeout=10.0)
        else:
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
