from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Literal
import uuid

import httpx

from qmtl.common import AsyncCircuitBreaker
from qmtl.common.compute_context import (
    ComputeContext,
    build_worldservice_compute_context,
)
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


ExecutionDomain = Literal["backtest", "dryrun", "live", "shadow"]


def _assemble_compute_context(world_id: str, payload: dict[str, Any]) -> ComputeContext:
    context = build_worldservice_compute_context(world_id, payload)
    if context.downgraded and context.downgrade_reason:
        gw_metrics.worlds_compute_context_downgrade_total.labels(
            reason=context.downgrade_reason
        ).inc()
    return context


def _augment_decision_payload(world_id: str, payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    if "effective_mode" not in payload:
        return payload
    context = _assemble_compute_context(world_id, payload)
    payload["execution_domain"] = context.execution_domain or None
    payload["compute_context"] = context.to_dict(include_flags=True)
    return payload


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
        """Poll the WorldService health endpoint until it is ready."""
        deadline = asyncio.get_running_loop().time() + timeout
        health_url = self._build_url("/health")
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
                raise RuntimeError("WorldService unavailable")
            await asyncio.sleep(0.5)

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base}{path}"

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

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
    ) -> Any:
        resp = await self._request(
            method,
            self._build_url(path),
            headers=headers,
            params=params,
            json=json,
        )
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    async def _request_no_content(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        resp = await self._request(
            method,
            self._build_url(path),
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        return None

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
                "GET",
                self._build_url(f"/worlds/{world_id}/decide"),
                headers=headers,
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
            augmented = _augment_decision_payload(world_id, data)
            self._decision_cache[world_id] = TTLCacheEntry(augmented, ttl)
            return augmented, False

        # Fallback to envelope ttl semantics when header is missing or <= 0
        tval = data.get("ttl") if isinstance(data, dict) else None
        if tval is None:
            # Spec default when envelope omits ttl
            augmented = _augment_decision_payload(world_id, data)
            self._decision_cache[world_id] = TTLCacheEntry(augmented, 300)
            return augmented, False

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
            return _augment_decision_payload(world_id, data), False
        if env_ttl <= 0:
            # Explicit no-cache
            return _augment_decision_payload(world_id, data), False

        augmented = _augment_decision_payload(world_id, data)
        self._decision_cache[world_id] = TTLCacheEntry(augmented, env_ttl)
        return augmented, False

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
                self._build_url(f"/worlds/{world_id}/activation"),
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
        return await self._request_json("GET", "/worlds", headers=headers)

    async def create_world(self, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "POST", "/worlds", headers=headers, json=payload
        )

    async def get_world(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "GET", f"/worlds/{world_id}", headers=headers
        )

    async def put_world(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "PUT",
            f"/worlds/{world_id}",
            headers=headers,
            json=payload,
        )

    async def delete_world(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> None:
        await self._request_no_content(
            "DELETE", f"/worlds/{world_id}", headers=headers
        )

    async def post_policy(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/policies",
            headers=headers,
            json=payload,
        )

    async def get_policies(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "GET", f"/worlds/{world_id}/policies", headers=headers
        )

    async def set_default_policy(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/set-default",
            headers=headers,
            json=payload,
        )

    async def post_bindings(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/bindings",
            headers=headers,
            json=payload,
        )

    async def get_bindings(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "GET", f"/worlds/{world_id}/bindings", headers=headers
        )

    async def post_decisions(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/decisions",
            headers=headers,
            json=payload,
        )

    async def put_activation(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "PUT",
            f"/worlds/{world_id}/activation",
            headers=headers,
            json=payload,
        )

    async def get_audit(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "GET", f"/worlds/{world_id}/audit", headers=headers
        )
    async def get_state_hash(
        self,
        world_id: str,
        topic: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Fetch state hash for a topic without retrieving full snapshot."""

        return await self._request_json(
            "GET",
            f"/worlds/{world_id}/{topic}/state_hash",
            headers=headers,
        )

    async def post_evaluate(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/evaluate",
            headers=headers,
            json=payload,
        )

    async def post_apply(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/apply",
            headers=headers,
            json=payload,
        )


__all__ = ["Budget", "WorldServiceClient", "ExecutionDomain", "ComputeContext"]
