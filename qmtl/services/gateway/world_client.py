from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

import httpx

from qmtl.foundation.common import AsyncCircuitBreaker
from qmtl.foundation.common.compute_context import ComputeContext

from . import metrics as gw_metrics
from .caches import ActivationCache, ActivationCacheEntry, TTLCache, TTLCacheResult
from .transport import BreakerRetryTransport
from .world_payloads import augment_activation_payload, augment_decision_payload

_RETRYABLE_STALE_4XX_STATUSES = {408, 429}


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
            on_open=self._on_breaker_open,
            on_close=self._on_breaker_close,
            on_failure=self._on_breaker_failure,
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

    @property
    def base_url(self) -> str:
        return self._base

    @property
    def http_client(self) -> httpx.AsyncClient:
        return self._client

    def _on_breaker_open(self) -> None:
        gw_metrics.worlds_breaker_state.set(1)
        gw_metrics.worlds_breaker_open_total.inc()

    def _on_breaker_close(self) -> None:
        gw_metrics.worlds_breaker_state.set(0)
        gw_metrics.worlds_breaker_failures.set(0)

    def _on_breaker_failure(self, count: int) -> None:
        gw_metrics.worlds_breaker_failures.set(count)

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
        self,
        world_id: str,
        as_of: str | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple[Any, bool]:
        normalized_as_of = self._normalize_as_of(as_of)
        cache_key = self._decision_cache_key(world_id, normalized_as_of)
        cached: TTLCacheResult[Any] = self._decision_cache.lookup(cache_key)
        if cached.fresh:
            gw_metrics.record_worlds_cache_hit()
            return cached.value, False
        result = await self._fetch_decide_response(
            world_id,
            normalized_as_of,
            headers,
            cached,
        )
        if not isinstance(result, httpx.Response):
            payload, stale = result
            if stale:
                payload = self._build_stale_decision_failsafe(
                    world_id=world_id,
                    cached_payload=payload,
                )
            return payload, stale

        resp: httpx.Response = result
        resp.raise_for_status()
        data = resp.json()
        cache_control = resp.headers.get("Cache-Control", "")
        augmented = augment_decision_payload(world_id, data)
        ttl = self._compute_decide_ttl(data, cache_control)
        if ttl > 0:
            self._decision_cache.set(cache_key, augmented, ttl)
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
                return (
                    self._build_stale_activation_failsafe(
                        world_id=world_id,
                        strategy_id=strategy_id,
                        side=side,
                        cached_entry=cached_entry,
                    ),
                    True,
                )
            raise
        if resp.status_code == 304 and cached_entry is not None:
            gw_metrics.record_worlds_cache_hit()
            return cached_payload, False
        if self._is_stale_fallback_status(resp.status_code) and cached_entry is not None:
            gw_metrics.record_worlds_stale_response()
            return (
                self._build_stale_activation_failsafe(
                    world_id=world_id,
                    strategy_id=strategy_id,
                    side=side,
                    cached_entry=cached_entry,
                ),
                True,
            )
        resp.raise_for_status()
        data = augment_activation_payload(resp.json())
        new_etag = resp.headers.get("ETag")
        if new_etag:
            self._activation_cache.set(key, new_etag, data)
        return data, False

    def _build_stale_activation_failsafe(
        self,
        *,
        world_id: str,
        strategy_id: str,
        side: str,
        cached_entry: ActivationCacheEntry[Any],
    ) -> dict[str, Any]:
        cached_payload = cached_entry.payload
        payload = dict(cached_payload) if isinstance(cached_payload, dict) else {}
        payload.setdefault("world_id", world_id)
        payload.setdefault("strategy_id", strategy_id)
        payload.setdefault("side", side)
        payload.setdefault("etag", cached_entry.etag)
        payload["effective_mode"] = "compute-only"
        payload["active"] = False
        payload["weight"] = 0.0
        payload.pop("execution_domain", None)
        payload.pop("compute_context", None)
        augmented = augment_activation_payload(payload)
        if isinstance(augmented, dict):
            return augmented
        return payload

    def _build_stale_decision_failsafe(
        self,
        *,
        world_id: str,
        cached_payload: Any,
    ) -> Any:
        if not isinstance(cached_payload, dict):
            return cached_payload

        payload = dict(cached_payload)
        has_compute_contract = any(
            field in payload
            for field in ("effective_mode", "execution_domain", "compute_context")
        )
        if not has_compute_contract:
            return payload

        payload.setdefault("world_id", world_id)
        payload["effective_mode"] = "compute-only"
        payload.pop("execution_domain", None)
        payload.pop("compute_context", None)
        augmented = augment_decision_payload(world_id, payload)
        if isinstance(augmented, dict):
            return augmented
        return payload

    async def _fetch_decide_response(
        self,
        world_id: str,
        as_of: str | None,
        headers: Optional[Dict[str, str]],
        cached: TTLCacheResult[Any],
    ) -> httpx.Response | tuple[Any, bool]:
        params = {"as_of": as_of} if as_of else None
        try:
            resp = await self._request(
                "GET",
                self._build_url(f"/worlds/{world_id}/decide"),
                headers=headers,
                params=params,
            )
        except Exception:
            if cached.present:
                gw_metrics.record_worlds_stale_response()
                return cached.value, True
            raise
        if self._is_stale_fallback_status(resp.status_code) and cached.present:
            gw_metrics.record_worlds_stale_response()
            return cached.value, True
        return resp

    @staticmethod
    def _is_stale_fallback_status(status_code: int) -> bool:
        return status_code >= 500 or status_code in _RETRYABLE_STALE_4XX_STATUSES

    @staticmethod
    def _normalize_as_of(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    def _decision_cache_key(self, world_id: str, as_of: str | None) -> str:
        if as_of is None:
            return world_id
        return f"{world_id}:as_of:{as_of}"

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

    async def describe_world(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "GET", f"/worlds/{world_id}/describe", headers=headers
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

    async def get_decisions(self, world_id: str, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "GET",
            f"/worlds/{world_id}/decisions",
            headers=headers,
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

    async def get_allocations(
        self,
        world_id: str | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        params = {"world_id": world_id} if world_id else None
        return await self._request_json(
            "GET",
            "/allocations",
            headers=headers,
            params=params,
        )

    async def get_evaluation_runs(
        self,
        world_id: str,
        strategy_id: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "GET",
            f"/worlds/{world_id}/strategies/{strategy_id}/runs",
            headers=headers,
        )

    async def get_evaluation_run(
        self,
        world_id: str,
        strategy_id: str,
        run_id: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "GET",
            f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}",
            headers=headers,
        )

    async def get_evaluation_run_metrics(
        self,
        world_id: str,
        strategy_id: str,
        run_id: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "GET",
            f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/metrics",
            headers=headers,
        )

    async def get_evaluation_run_history(
        self,
        world_id: str,
        strategy_id: str,
        run_id: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "GET",
            f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/history",
            headers=headers,
        )

    async def post_ex_post_failure(
        self,
        world_id: str,
        strategy_id: str,
        run_id: str,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/ex-post-failures",
            headers=headers,
            json=payload,
        )

    async def post_evaluate(self, world_id: str, payload: Any, headers: Optional[Dict[str, str]] = None) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/evaluate",
            headers=headers,
            json=payload,
        )

    async def post_evaluation_override(
        self,
        world_id: str,
        strategy_id: str,
        run_id: str,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/override",
            headers=headers,
            json=payload,
        )

    async def post_live_promotion_approve(
        self,
        world_id: str,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/promotions/live/approve",
            headers=headers,
            json=payload,
        )

    async def post_live_promotion_reject(
        self,
        world_id: str,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/promotions/live/reject",
            headers=headers,
            json=payload,
        )

    async def get_live_promotion_plan(
        self,
        world_id: str,
        *,
        strategy_id: str,
        run_id: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "GET",
            f"/worlds/{world_id}/promotions/live/plan",
            headers=headers,
            params={"strategy_id": strategy_id, "run_id": run_id},
        )

    async def get_live_promotion_candidates(
        self,
        world_id: str,
        *,
        limit: int = 20,
        include_plan: bool = False,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "GET",
            f"/worlds/{world_id}/promotions/live/candidates",
            headers=headers,
            params={"limit": limit, "include_plan": include_plan},
        )

    async def get_campaign_status(
        self,
        world_id: str,
        *,
        strategy_id: str | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        params: Dict[str, Any] = {}
        if strategy_id is not None:
            params["strategy_id"] = strategy_id
        return await self._request_json(
            "GET",
            f"/worlds/{world_id}/campaign/status",
            headers=headers,
            params=params or None,
        )

    async def post_campaign_tick(
        self,
        world_id: str,
        *,
        strategy_id: str | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        params: Dict[str, Any] = {}
        if strategy_id is not None:
            params["strategy_id"] = strategy_id
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/campaign/tick",
            headers=headers,
            params=params or None,
            json={},
        )

    async def post_live_promotion_apply(
        self,
        world_id: str,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/promotions/live/apply",
            headers=headers,
            json=payload,
        )

    async def post_live_promotion_auto_apply(
        self,
        world_id: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        return await self._request_json(
            "POST",
            f"/worlds/{world_id}/promotions/live/auto-apply",
            headers=headers,
            json={},
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
