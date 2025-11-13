from __future__ import annotations

import base64
import json
from typing import Any, Optional

import httpx
from opentelemetry.propagate import inject
from pydantic import ValidationError

from qmtl.foundation.common import AsyncCircuitBreaker, crc32_of_list
from qmtl.services.gateway.models import StrategyAck
from . import runtime


class GatewayClient:
    """HTTP client for communicating with the Gateway service."""

    def __init__(self, circuit_breaker: AsyncCircuitBreaker | None = None) -> None:
        self._circuit_breaker = circuit_breaker or AsyncCircuitBreaker(max_failures=3)

    def set_circuit_breaker(self, cb: AsyncCircuitBreaker | None) -> None:
        """Replace the current circuit breaker."""
        self._circuit_breaker = cb or AsyncCircuitBreaker(max_failures=3)

    async def post_strategy(
        self,
        *,
        gateway_url: str,
        dag: dict,
        meta: Optional[dict],
        context: Optional[dict[str, str]] = None,
        world_id: Optional[str] = None,
    ) -> StrategyAck | dict[str, object]:
        """Submit a strategy DAG to the gateway."""
        url = gateway_url.rstrip("/") + "/strategies"
        payload = {
            "dag_json": base64.b64encode(json.dumps(dag).encode()).decode(),
            "meta": meta,
            "node_ids_crc32": crc32_of_list(n["node_id"] for n in dag.get("nodes", [])),
        }
        if world_id is not None:
            payload["world_id"] = world_id
        if context:
            payload["context"] = context
        headers: dict[str, str] = {}
        inject(headers)
        try:
            client = httpx.AsyncClient(headers=headers, timeout=runtime.HTTP_TIMEOUT_SECONDS)
        except TypeError:
            client = httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS)
        try:
            client.headers.update(headers)  # type: ignore[attr-defined]
        except Exception:
            pass
        async with client:
            post_fn = client.post
            if self._circuit_breaker is not None:
                post_fn = self._circuit_breaker(post_fn)
            try:
                resp = await post_fn(url, json=payload)
            except Exception as exc:  # pragma: no cover - network errors
                return {"error": str(exc)}
        if resp.status_code == 202:
            if self._circuit_breaker is not None:
                self._circuit_breaker.reset()
            payload = resp.json()
            try:
                if hasattr(StrategyAck, "model_validate"):
                    ack = StrategyAck.model_validate(payload)  # type: ignore[attr-defined]
                else:  # pragma: no cover - pydantic v1 fallback
                    ack = StrategyAck.parse_obj(payload)  # type: ignore[attr-defined]
            except ValidationError:
                return {"error": "invalid gateway response"}
            return ack
        if resp.status_code == 409:
            return {"error": "duplicate strategy"}
        if resp.status_code == 422:
            return {"error": "invalid strategy payload"}
        return {"error": f"gateway error {resp.status_code}"}

    async def post_history_metadata(
        self,
        *,
        gateway_url: str,
        strategy_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Publish Seamless history metadata to Gateway."""

        url = gateway_url.rstrip("/") + f"/strategies/{strategy_id}/history"
        headers: dict[str, str] = {}
        inject(headers)
        try:
            client = httpx.AsyncClient(headers=headers, timeout=runtime.HTTP_TIMEOUT_SECONDS)
        except TypeError:
            client = httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS)
        try:
            client.headers.update(headers)  # type: ignore[attr-defined]
        except Exception:
            pass

        async with client:
            post_fn = client.post
            if self._circuit_breaker is not None:
                post_fn = self._circuit_breaker(post_fn)
            try:
                resp = await post_fn(url, json=payload)
            except Exception as exc:  # pragma: no cover - network errors
                return {"error": str(exc)}

        if resp.status_code >= 400:
            return {"error": f"gateway error {resp.status_code}"}
        if resp.content:
            try:
                return resp.json()
            except Exception:  # pragma: no cover - non-JSON payloads
                return None
        return None

    async def get_health(
        self,
        *,
        gateway_url: str,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Fetch the Gateway health endpoint."""

        url = gateway_url.rstrip("/") + "/health"
        try:
            async with httpx.AsyncClient(headers=headers, timeout=runtime.HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                if resp.content:
                    return resp.json()
                return {}
        except Exception:
            return {}
