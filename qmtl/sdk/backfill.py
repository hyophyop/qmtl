from __future__ import annotations

"""Backfill data sources."""

from typing import Protocol

import pandas as pd


class BackfillSource(Protocol):
    """Interface for fetching historical data for nodes."""

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Return data in ``[start, end)`` for ``node_id`` and ``interval``."""
        ...


