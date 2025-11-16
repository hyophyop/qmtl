from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

import httpx

from qmtl.foundation.common import AsyncCircuitBreaker
from qmtl.foundation.common.compute_context import ComputeContext

from . import metrics as gw_metrics
from .caches import ActivationCache, TTLCache, TTLCacheResult
from .transport import BreakerRetryTransport
from .world_payloads import augment_activation_payload, augment_decision_payload


@dataclass
class Budget:
    """Request budget configuration."""

    timeout: float = 0.3
    retries: int = 2


ExecutionDomain = Literal["backtest", "dryrun", "live", "shadow"]


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
        rebalance_schema_version: int = 1,
        alpha_metrics_capable: bool = False,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._budget = budget or Budget()
        self._client = client or httpx.AsyncClient()
        self._decision_cache: TTLCache[Any] = TTLCache()
        self._activation_cache: ActivationCache[Any] = ActivationCache()
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

        async def _backoff(_: int, __: Exception) -> None:
            await self._wait_for_service()

        def _after_success(_: AsyncCircuitBreaker) -> None:
            gw_metrics.worlds_breaker_failures.set(self._breaker.failures)

        self._transport = BreakerRetryTransport(
            self._client,
            self._breaker,
            timeout=self._budget.timeout,
            retries=self._budget.retries,
            wait_for_service=_backoff,
            observe_latency=gw_metrics.observe_worlds_proxy_latency,
            on_success=_after_success,
        )
        self._rebalance_schema_version = max(1, rebalance_schema_version or 1)
        self._alpha_metrics_capable = bool(alpha_metrics_capable)

    def configure_rebalance_capabilities(
        self,
        *,
        schema_version: int | None = None,
        alpha_metrics_capable: bool | None = None,
    ) -> None:
        if schema_version is not None:
            self._rebalance_schema_version = max(1, schema_version)
        if alpha_metrics_capable is not None:
            self._alpha_metrics_capable = bool(alpha_metrics_capable)

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
        return await self._transport.request(method, url, **kwargs)

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
        cached: TTLCacheResult[Any] = self._decision_cache.lookup(world_id)
        if cached.fresh:
            gw_metrics.record_worlds_cache_hit()
            return cached.value, False
        result = await self._fetch_decide_response(world_id, headers, cached)
        if not isinstance(result, httpx.Response):
            payload, stale = result
            return payload, stale

        resp: httpx.Response = result
        resp.raise_for_status()
        data = resp.json()
        cache_control = resp.headers.get("Cache-Control", "")
        augmented = augment_decision_payload(world_id, data)
        ttl = self._compute_decide_ttl(data, cache_control)
        if ttl > 0:
            self._decision_cache.set(world_id, augmented, ttl)
        return augmented, False

    async def get_activation(
        self,
        world_id: str,
        strategy_id: str,
        side: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple[Any, bool]:
        key = f"{world_id}:{strategy_id}:{side}"
        cached_entry = self._activation_cache.get(key)
        cached_payload = cached_entry.payload if cached_entry else None
        req_headers = self._activation_cache.conditional_headers(key, headers)
        try:
            resp = await self._request(
                "GET",
                self._build_url(f"/worlds/{world_id}/activation"),
                headers=req_headers,
                params={"strategy_id": strategy_id, "side": side},
            )
        except Exception:
            if cached_entry is not None:
                gw_metrics.record_worlds_stale_response()
                return cached_payload, True
            raise
        if resp.status_code == 304 and cached_entry is not None:
            gw_metrics.record_worlds_cache_hit()
            return cached_payload, False
        if resp.status_code >= 500 and cached_entry is not None:
            gw_metrics.record_worlds_stale_response()
            return cached_payload, True
        resp.raise_for_status()
        data = augment_activation_payload(resp.json())
        new_etag = resp.headers.get("ETag")
        if new_etag:
            self._activation_cache.set(key, new_etag, data)
        return data, False

    async def _fetch_decide_response(
        self,
        world_id: str,
        headers: Optional[Dict[str, str]],
        cached: TTLCacheResult[Any],
    ) -> httpx.Response | tuple[Any, bool]:
        try:
            resp = await self._request(
                "GET",
                self._build_url(f"/worlds/{world_id}/decide"),
                headers=headers,
            )
        except Exception:
            if cached.present:
                gw_metrics.record_worlds_stale_response()
                return cached.value, True
            raise
        if resp.status_code >= 500 and cached.present:
            gw_metrics.record_worlds_stale_response()
            return cached.value, True
        return resp

    def _compute_decide_ttl(self, data: Any, cache_control: str) -> int:
        ttl = self._ttl_from_cache_control(cache_control)
        if ttl > 0:
            return ttl
        tval = data.get("ttl") if isinstance(data, dict) else None
        if tval is None:
            return 300
        env_ttl = self._ttl_from_envelope_value(tval)
        if env_ttl is None or env_ttl <= 0:
            return 0
        return env_ttl

    def _ttl_from_cache_control(self, cache_control: str) -> int:
        if "max-age=" not in cache_control:
            return 0
        try:
            return int(cache_control.split("max-age=")[1].split(",")[0])
        except Exception:
            return 0

    def _ttl_from_envelope_value(self, tval: Any) -> int | None:
        if isinstance(tval, str):
            if tval.endswith("s"):
                try:
                    return int(tval[:-1])
                except Exception:
                    return None
            return None
        if isinstance(tval, (int, float)):
            return int(tval)
        return None


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

    async def post_history_metadata(
        self,
        world_id: str,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        resp = await self._request(
            "POST",
            self._build_url(f"/worlds/{world_id}/history"),
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

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

    async def post_rebalance_plan(
        self,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
        *,
        schema_version: int | None = None,
        fallback_schema_version: int | None = None,
    ) -> Any:
        """Request a multi-world rebalance plan from WorldService.

        This proxies to the WorldService endpoint at ``/rebalancing/plan``.
        """
        attempts = list(
            self._iter_rebalance_payloads(
                payload,
                schema_version=schema_version,
                fallback_schema_version=fallback_schema_version,
            )
        )
        last_exc: httpx.HTTPStatusError | None = None
        for version, body in attempts:
            try:
                return await self._request_json(
                    "POST",
                    "/rebalancing/plan",
                    headers=headers,
                    json=body,
                )
            except httpx.HTTPStatusError as exc:
                if not self._should_retry_rebalance_version(version, exc):
                    raise
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("no payload variants generated for rebalance plan")

    def _iter_rebalance_payloads(
        self,
        payload: Any,
        *,
        schema_version: int | None = None,
        fallback_schema_version: int | None = None,
    ) -> list[tuple[int, dict[str, Any]]]:
        preferred = self._preferred_schema_version(schema_version)
        versions = self._rebalance_versions(preferred, fallback_schema_version)
        base_payload = dict(payload)
        base_payload.pop("schema_version", None)

        variants: list[tuple[int, dict[str, Any]]] = []
        for version in versions:
            body = dict(base_payload)
            if version > 1:
                body["schema_version"] = version
            variants.append((version, body))
        return variants

    def _preferred_schema_version(self, explicit: int | None) -> int:
        if explicit is not None:
            return max(1, explicit)
        return max(1, self._rebalance_schema_version or 1)

    @staticmethod
    def _rebalance_versions(preferred: int, fallback: int | None) -> list[int]:
        versions: list[int] = []
        if preferred > 1:
            versions.append(preferred)
        fallback_version = max(1, fallback) if fallback is not None else (1 if preferred > 1 else None)
        if fallback_version is not None and fallback_version not in versions:
            versions.append(fallback_version)
        if preferred == 1 and not versions:
            versions.append(1)
        return versions

    def _should_retry_rebalance_version(
        self,
        attempted_version: int,
        exc: httpx.HTTPStatusError,
    ) -> bool:
        if attempted_version <= 1:
            return False
        status = exc.response.status_code
        return status in {400, 404, 415, 422, 501}


__all__ = ["Budget", "WorldServiceClient", "ExecutionDomain", "ComputeContext"]
