import httpx
import pandas as pd

from qmtl.sdk import DataFetcher


class BinanceFetcher:
    """Retrieve kline history from Binance."""

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: str
    ) -> pd.DataFrame:
        url = (
            "https://api.binance.com/api/v3/klines"
            f"?symbol={node_id}&interval={interval}"
            f"&startTime={start * 1000}&endTime={end * 1000}"
        )
        async with httpx.AsyncClient() as client:
            data = (await client.get(url)).json()
        return pd.DataFrame(
            [
                {"ts": int(r[0] / 1000), "open": float(r[1]), "close": float(r[4])}
                for r in data
            ]
        )
