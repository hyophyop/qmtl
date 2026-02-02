import polars as pl

from qmtl.runtime.sdk import DataFetcher


class DummyDataFetcher:
    """A simple DataFetcher returning predetermined rows."""

    def __init__(self, rows=None):
        if rows is None:
            rows = [
                {"ts": 120, "value": 1},
                {"ts": 180, "value": 2},
            ]
        self.df = pl.DataFrame(rows)

    async def fetch(self, start, end, *, node_id, interval):
        # ignore parameters and return the stored dataframe
        return self.df

