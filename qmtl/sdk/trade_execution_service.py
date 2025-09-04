from __future__ import annotations

"""Service for posting trade orders to a broker API with retries."""

from typing import Any
import time

import httpx

from .http import HttpPoster


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
                response = HttpPoster.post(self.url, json=order)
                response.raise_for_status()
                return response
            except Exception:
                attempt += 1
                status = self.poll_order_status(order)
                if status is not None:
                    return status
                if attempt > self.max_retries:
                    raise

    def poll_order_status(self, order: Any) -> httpx.Response | None:
        """Query broker for the status of ``order`` until completion.

        Returns the status response when the order is reported as completed,
        otherwise ``None`` if the order is not found or still pending.
        """
        order_id = getattr(order, "id", None)
        if order_id is None:
            order_id = order.get("id") if isinstance(order, dict) else None
        if order_id is None:
            return None
        deadline = time.time() + (self.backoff * self.max_retries)
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{self.url}/{order_id}", timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") in {"filled", "done", "completed"}:
                    return resp
            except Exception:
                pass
            time.sleep(self.backoff)
        return None
