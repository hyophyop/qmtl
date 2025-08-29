from __future__ import annotations

"""WorldService HTTP proxy client with in-memory caching."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional, Dict

import httpx

from . import metrics as gw_metrics


@dataclass
class _DecisionCacheEntry:
    data: Dict[str, Any]
    expires_at: float
    etag: Optional[str]


@dataclass
class _ActivationCacheEntry:
    data: Dict[str, Any]
    etag: Optional[str]


class WorldClient:
    """Async HTTP client for WorldService with basic caching."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 0.3,
        retries: int = 2,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self._client = http_client or httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
        self._decision_cache: Dict[str, _DecisionCacheEntry] = {}
        self._activation_cache: Dict[str, _ActivationCacheEntry] = {}

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return await self._client.request(method, url, **kwargs)
            except httpx.RequestError as exc:  # pragma: no cover - network failure
                last_exc = exc
                if attempt < self.retries:
                    await asyncio.sleep(0.05)
        assert last_exc is not None
        raise last_exc

    async def get_decision(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        entry = self._decision_cache.get(world_id)
        now = time.time()
        if entry and entry.expires_at > now:
            gw_metrics.worldservice_cache_hits_total.labels(endpoint="decide").inc()
            return entry.data

        start = time.perf_counter()
        resp = await self._request("GET", f"/worlds/{world_id}/decide", headers=headers)
        duration_ms = (time.perf_counter() - start) * 1000
        gw_metrics.worldservice_latency_ms.labels(endpoint="decide").set(duration_ms)
        resp.raise_for_status()
        data = resp.json()
        ttl = float(data.get("ttl", 300))
        self._decision_cache[world_id] = _DecisionCacheEntry(
            data=data, expires_at=now + ttl, etag=resp.headers.get("ETag")
        )
        return data

    async def get_activation(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        entry = self._activation_cache.get(world_id)
        req_headers = dict(headers or {})
        if entry and entry.etag:
            req_headers["If-None-Match"] = entry.etag

        start = time.perf_counter()
        resp = await self._request("GET", f"/worlds/{world_id}/activation", headers=req_headers)
        duration_ms = (time.perf_counter() - start) * 1000
        gw_metrics.worldservice_latency_ms.labels(endpoint="activation").set(duration_ms)

        if resp.status_code == 304 and entry:
            gw_metrics.worldservice_cache_hits_total.labels(endpoint="activation").inc()
            return entry.data

        resp.raise_for_status()
        data = resp.json()
        etag = resp.headers.get("ETag") or data.get("state_hash")
        self._activation_cache[world_id] = _ActivationCacheEntry(data=data, etag=etag)
        return data

    async def post_evaluate(
        self, world_id: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        resp = await self._request(
            "POST", f"/worlds/{world_id}/evaluate", headers=headers, json=payload
        )
        duration_ms = (time.perf_counter() - start) * 1000
        gw_metrics.worldservice_latency_ms.labels(endpoint="evaluate").set(duration_ms)
        resp.raise_for_status()
        return resp.json()

    async def post_apply(
        self, world_id: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        resp = await self._request(
            "POST", f"/worlds/{world_id}/apply", headers=headers, json=payload
        )
        duration_ms = (time.perf_counter() - start) * 1000
        gw_metrics.worldservice_latency_ms.labels(endpoint="apply").set(duration_ms)
        resp.raise_for_status()
        return resp.json()

