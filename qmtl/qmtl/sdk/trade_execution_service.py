from __future__ import annotations

"""Service for posting trade orders to a broker API with retries."""

from typing import Any
import time

import httpx


class TradeExecutionService:
    """Post trade orders to a broker with retry logic."""

    def __init__(self, url: str, *, max_retries: int = 3, backoff: float = 0.1) -> None:
        self.url = url
        self.max_retries = max_retries
        self.backoff = backoff

    def post_order(self, order: Any) -> httpx.Response:
        """Send ``order`` to the broker API, retrying on failure."""
        attempt = 0
        while True:
            try:
                response = httpx.post(self.url, json=order, timeout=10.0)
                response.raise_for_status()
                return response
            except Exception:
                attempt += 1
                if attempt > self.max_retries:
                    raise
                time.sleep(self.backoff * attempt)
