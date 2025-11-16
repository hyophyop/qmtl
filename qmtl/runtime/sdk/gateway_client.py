from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from opentelemetry.propagate import inject
from pydantic import ValidationError

from qmtl.foundation.common import AsyncCircuitBreaker, crc32_of_list
from qmtl.services.gateway.models import StrategyAck
from . import runtime


@dataclass
class GatewayCallResult:
    """Captured result of a gateway invocation."""

    status_code: int | None
    payload: Any | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and (self.status_code or 0) < 400


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
        payload = self._build_strategy_payload(dag, meta, context, world_id)
        headers = self._build_headers()
        result = await self._post(url, payload, headers)
        return self._parse_strategy_response(result)

    async def post_history_metadata(
        self,
        *,
        gateway_url: str,
        strategy_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Publish Seamless history metadata to Gateway."""

        url = gateway_url.rstrip("/") + f"/strategies/{strategy_id}/history"
        headers = self._build_headers()
        result = await self._post(url, payload, headers)

        if result.error:
            return {"error": result.error}

        status = result.status_code or 0
        if status >= 400:
            return {"error": f"gateway error {status}"}
        if result.payload is not None:
            return result.payload
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

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        inject(headers)
        return headers

    def _build_strategy_payload(
        self,
        dag: dict,
        meta: Optional[dict],
        context: Optional[dict[str, str]],
        world_id: Optional[str],
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "dag_json": base64.b64encode(json.dumps(dag).encode()).decode(),
            "meta": meta,
            "node_ids_crc32": crc32_of_list(n["node_id"] for n in dag.get("nodes", [])),
        }
        if world_id is not None:
            payload["world_id"] = world_id
        if context:
            payload["context"] = context
        return payload

    def _create_client(self, headers: dict[str, str]) -> httpx.AsyncClient:
        try:
            return httpx.AsyncClient(headers=headers, timeout=runtime.HTTP_TIMEOUT_SECONDS)
        except TypeError:
            return httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS)

    def _wrap_post(self, client: httpx.AsyncClient):
        post_fn = client.post
        if self._circuit_breaker is not None:
            post_fn = self._circuit_breaker(post_fn)
        return post_fn

    async def _post(
        self, url: str, payload: dict[str, object], headers: dict[str, str]
    ) -> GatewayCallResult:
        client = self._create_client(headers)
        self._attach_headers(client, headers)
        async with client:
            post_fn = self._wrap_post(client)
            try:
                resp = await post_fn(url, json=payload)
            except Exception as exc:  # pragma: no cover - network errors
                return GatewayCallResult(status_code=None, error=str(exc))
        return GatewayCallResult(
            status_code=resp.status_code,
            payload=self._safe_json(resp),
        )

    def _attach_headers(self, client: httpx.AsyncClient, headers: dict[str, str]) -> None:
        try:
            client.headers.update(headers)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _safe_json(self, resp: httpx.Response) -> Any | None:
        try:
            return resp.json()
        except Exception:  # pragma: no cover - non-JSON payloads
            return None

    def _parse_strategy_response(
        self, result: GatewayCallResult
    ) -> StrategyAck | dict[str, object]:
        error = self._extract_error_message(result)
        if error is not None:
            return {"error": error}

        status = result.status_code or 0
        if status != 202:
            return {"error": self._status_error_message(status)}

        self._reset_breaker()
        payload = self._strategy_payload_dict(result.payload)
        if payload is None:
            return {"error": "invalid gateway response"}

        normalized = self._ensure_queue_map(payload)
        if normalized is None:
            return {"error": "invalid gateway response"}

        try:
            return self._build_strategy_ack(normalized)
        except ValidationError:
            return {"error": "invalid gateway response"}

    def _extract_error_message(self, result: GatewayCallResult) -> str | None:
        if result.error:
            return result.error
        return None

    def _status_error_message(self, status: int) -> str:
        if status == 409:
            return "duplicate strategy"
        if status == 422:
            return "invalid strategy payload"
        return f"gateway error {status}"

    def _strategy_payload_dict(self, payload: Any | None) -> dict[str, object] | None:
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            return None
        return payload

    def _ensure_queue_map(self, payload: dict[str, object]) -> dict[str, object] | None:
        if "queue_map" in payload:
            return payload
        strategy_id = payload.get("strategy_id")
        if isinstance(strategy_id, str):
            merged: dict[str, object] = dict(payload)
            merged.setdefault("queue_map", {})
            return merged
        return None

    def _build_strategy_ack(self, payload: dict[str, object]) -> StrategyAck:
        if hasattr(StrategyAck, "model_validate"):
            return StrategyAck.model_validate(payload)  # type: ignore[attr-defined]
        return StrategyAck.parse_obj(payload)  # type: ignore[attr-defined]

    def _reset_breaker(self) -> None:
        if self._circuit_breaker is not None:
            self._circuit_breaker.reset()
