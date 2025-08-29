from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from . import metrics as gw_metrics


@dataclass
class Budget:
    """Request budget configuration."""

    timeout: float = 5.0
    retries: int = 0


class TTLCacheEntry:
    """Internal structure for TTL cached items."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: float) -> None:
        self.value = value
        self.expires_at = time.time() + ttl

    def valid(self) -> bool:
        return time.time() < self.expires_at


class WorldServiceClient:
    """HTTP client proxying requests to WorldService.

    Implements simple TTL cache for decision envelopes and
    ETag-based caching for activations.
    """

    def __init__(
        self,
        base_url: str,
        *,
        budget: Budget | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._budget = budget or Budget()
        self._client = client or httpx.AsyncClient()
        self._decision_cache: Dict[str, TTLCacheEntry] = {}
        self._activation_cache: Dict[str, tuple[str, Any]] = {}

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        backoff = 0.1
        for attempt in range(self._budget.retries + 1):
            try:
                start = time.perf_counter()
                resp = await self._client.request(method, url, timeout=self._budget.timeout, **kwargs)
                gw_metrics.observe_worlds_proxy_latency((time.perf_counter() - start) * 1000)
                return resp
            except Exception:
                if attempt == self._budget.retries:
                    raise
                await asyncio.sleep(backoff)
                backoff *= 2
        raise RuntimeError("unreachable")

    async def get_decide(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        entry = self._decision_cache.get(world_id)
        if entry and entry.valid():
            gw_metrics.worlds_cache_hits_total.inc()
            gw_metrics.worlds_cache_hits_total._val = gw_metrics.worlds_cache_hits_total._value.get()  # type: ignore[attr-defined]
            return entry.value
        resp = await self._request("GET", f"{self._base}/worlds/{world_id}/decide", headers=headers)
        resp.raise_for_status()
        data = resp.json()
        cache_control = resp.headers.get("Cache-Control", "")
        ttl = 0
        if "max-age=" in cache_control:
            try:
                ttl = int(cache_control.split("max-age=")[1].split(",")[0])
            except Exception:
                ttl = 0
        if ttl > 0:
            self._decision_cache[world_id] = TTLCacheEntry(data, ttl)
        return data

    async def get_activation(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        etag, cached = self._activation_cache.get(world_id, (None, None))
        req_headers = dict(headers or {})
        if etag:
            req_headers["If-None-Match"] = etag
        resp = await self._request("GET", f"{self._base}/worlds/{world_id}/activation", headers=req_headers)
        if resp.status_code == 304 and cached is not None:
            gw_metrics.worlds_cache_hits_total.inc()
            gw_metrics.worlds_cache_hits_total._val = gw_metrics.worlds_cache_hits_total._value.get()  # type: ignore[attr-defined]
            return cached
        resp.raise_for_status()
        data = resp.json()
        new_etag = resp.headers.get("ETag")
        if new_etag:
            self._activation_cache[world_id] = (new_etag, data)
        return data

    async def post_evaluate(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request(
            "POST",
            f"{self._base}/worlds/{world_id}/evaluate",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def post_apply(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request(
            "POST",
            f"{self._base}/worlds/{world_id}/apply",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


__all__ = ["Budget", "WorldServiceClient"]
