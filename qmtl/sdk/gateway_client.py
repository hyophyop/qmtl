from __future__ import annotations

import base64
import json
from typing import Optional

import httpx
from opentelemetry.propagate import inject

from qmtl.common import AsyncCircuitBreaker, crc32_of_list
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
    ) -> dict:
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
            return resp.json().get("queue_map", {})
        if resp.status_code == 409:
            return {"error": "duplicate strategy"}
        if resp.status_code == 422:
            return {"error": "invalid strategy payload"}
        return {"error": f"gateway error {resp.status_code}"}
