from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
import uuid

import httpx

from qmtl.common import AsyncCircuitBreaker
from . import metrics as gw_metrics


@dataclass
class Budget:
    """Request budget configuration."""

    timeout: float = 0.3
    retries: int = 2


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
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._budget = budget or Budget()
        self._client = client or httpx.AsyncClient()
        self._decision_cache: Dict[str, TTLCacheEntry] = {}
        self._activation_cache: Dict[str, tuple[str, Any]] = {}
        self._breaker = breaker or AsyncCircuitBreaker(
            on_open=lambda: (
                gw_metrics.worlds_breaker_state.set(1),
                gw_metrics.worlds_breaker_open_total.inc(),
            ),
            on_close=lambda: (
                gw_metrics.worlds_breaker_state.set(0),
                gw_metrics.worlds_breaker_failures.set(0),
            ),
            on_failure=lambda c: gw_metrics.worlds_breaker_failures.set(c),
        )
        gw_metrics.worlds_breaker_state.set(0)
        gw_metrics.worlds_breaker_failures.set(0)

    async def _wait_for_service(self, timeout: float = 5.0) -> None:
        """Poll the world service health endpoint until it is ready."""
        deadline = asyncio.get_running_loop().time() + timeout
        health_url = f"{self._base}/health"
        while True:
            try:
                resp = await self._client.get(
                    health_url, timeout=self._budget.timeout
                )
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            if asyncio.get_running_loop().time() > deadline:
                raise RuntimeError("World service unavailable")
            await asyncio.sleep(0.5)

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        @self._breaker
        async def _call() -> httpx.Response:
            for attempt in range(self._budget.retries + 1):
                try:
                    start = time.perf_counter()
                    resp = await self._client.request(
                        method, url, timeout=self._budget.timeout, **kwargs
                    )
                    gw_metrics.observe_worlds_proxy_latency(
                        (time.perf_counter() - start) * 1000
                    )
                    return resp
                except Exception:
                    if attempt == self._budget.retries:
                        raise
                    await self._wait_for_service()
            raise RuntimeError("unreachable")

        resp = await _call()
        self._breaker.reset()
        gw_metrics.worlds_breaker_failures.set(self._breaker.failures)
        return resp

    @property
    def breaker(self) -> AsyncCircuitBreaker:
        return self._breaker

    async def get_decide(
        self, world_id: str, headers: Optional[Dict[str, str]] = None
    ) -> tuple[Any, bool]:
        entry = self._decision_cache.get(world_id)
        if entry and entry.valid():
            gw_metrics.record_worlds_cache_hit()
            return entry.value, False
        try:
            resp = await self._request(
                "GET", f"{self._base}/worlds/{world_id}/decide", headers=headers
            )
        except Exception:
            if entry is not None:
                gw_metrics.record_worlds_stale_response()
                return entry.value, True
            raise
        if resp.status_code >= 500 and entry is not None:
            gw_metrics.record_worlds_stale_response()
            return entry.value, True
        resp.raise_for_status()
        data = resp.json()
        cache_control = resp.headers.get("Cache-Control", "")
        ttl = 0
        if "max-age=" in cache_control:
            try:
                ttl = int(cache_control.split("max-age=")[1].split(",")[0])
            except Exception:
                ttl = 0

        # Header max-age takes precedence if positive
        if ttl > 0:
            self._decision_cache[world_id] = TTLCacheEntry(data, ttl)
            return data, False

        # Fallback to envelope ttl semantics when header is missing or <= 0
        tval = data.get("ttl") if isinstance(data, dict) else None
        if tval is None:
            # Spec default when envelope omits ttl
            self._decision_cache[world_id] = TTLCacheEntry(data, 300)
            return data, False

        # Envelope provided ttl; honor zero as "do not cache"
        env_ttl: int | None = None
        if isinstance(tval, str):
            if tval.endswith("s"):
                try:
                    env_ttl = int(tval[:-1])
                except Exception:
                    env_ttl = None
            else:
                # Not a supported format; treat as invalid → no cache
                env_ttl = None
        elif isinstance(tval, (int, float)):
            env_ttl = int(tval)

        if env_ttl is None:
            # Invalid ttl provided → be conservative and do not cache
            return data, False
        if env_ttl <= 0:
            # Explicit no-cache
            return data, False

        self._decision_cache[world_id] = TTLCacheEntry(data, env_ttl)
        return data, False

    async def get_activation(
        self,
        world_id: str,
        strategy_id: str,
        side: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple[Any, bool]:
        key = f"{world_id}:{strategy_id}:{side}"
        etag, cached = self._activation_cache.get(key, (None, None))
        req_headers = dict(headers or {})
        if etag:
            req_headers["If-None-Match"] = etag
        try:
            resp = await self._request(
                "GET",
                f"{self._base}/worlds/{world_id}/activation",
                headers=req_headers,
                params={"strategy_id": strategy_id, "side": side},
            )
        except Exception:
            if cached is not None:
                gw_metrics.record_worlds_stale_response()
                return cached, True
            raise
        if resp.status_code == 304 and cached is not None:
            gw_metrics.record_worlds_cache_hit()
            return cached, False
        if resp.status_code >= 500 and cached is not None:
            gw_metrics.record_worlds_stale_response()
            return cached, True
        resp.raise_for_status()
        data = resp.json()
        new_etag = resp.headers.get("ETag")
        if new_etag:
            self._activation_cache[key] = (new_etag, data)
        return data, False


    async def list_worlds(self, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("GET", f"{self._base}/worlds", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def create_world(self, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("POST", f"{self._base}/worlds", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_world(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("GET", f"{self._base}/worlds/{world_id}", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def put_world(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("PUT", f"{self._base}/worlds/{world_id}", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def delete_world(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> None:
        resp = await self._request("DELETE", f"{self._base}/worlds/{world_id}", headers=headers)
        resp.raise_for_status()

    async def post_policy(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("POST", f"{self._base}/worlds/{world_id}/policies", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_policies(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("GET", f"{self._base}/worlds/{world_id}/policies", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def set_default_policy(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("POST", f"{self._base}/worlds/{world_id}/set-default", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def post_bindings(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("POST", f"{self._base}/worlds/{world_id}/bindings", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_bindings(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("GET", f"{self._base}/worlds/{world_id}/bindings", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def post_decisions(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("POST", f"{self._base}/worlds/{world_id}/decisions", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def put_activation(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("PUT", f"{self._base}/worlds/{world_id}/activation", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_audit(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        resp = await self._request("GET", f"{self._base}/worlds/{world_id}/audit", headers=headers)
        resp.raise_for_status()
        return resp.json()
    async def get_state_hash(
        self,
        world_id: str,
        topic: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Fetch state hash for a topic without retrieving full snapshot."""

        resp = await self._request(
            "GET",
            f"{self._base}/worlds/{world_id}/{topic}/state_hash",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

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
