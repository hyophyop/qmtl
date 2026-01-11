"""WorldService activation client for exit engine updates."""

from __future__ import annotations

from typing import Any

import httpx

from .models import ExitAction


class WorldServiceActivationClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        auth_header: str = "Authorization",
        auth_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=self._build_headers(auth_header, auth_token),
        )
        self._owns_client = client is None

    def _build_headers(self, header: str, token: str | None) -> dict[str, str]:
        if token:
            return {header: f"Bearer {token}"}
        return {}

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def apply_action(self, action: ExitAction) -> dict[str, Any]:
        payload = {
            "strategy_id": action.strategy_id,
            "side": action.side,
            "active": False,
            "weight": 0.0,
            "run_id": action.run_id,
        }
        if action.action == "freeze":
            payload.update({"freeze": True, "drain": True})
        elif action.action == "drain":
            payload.update({"freeze": False, "drain": True})
        resp = await self._client.put(
            f"/worlds/{action.world_id}/activation",
            json=payload,
            headers={"X-Request-ID": action.request_id},
        )
        resp.raise_for_status()
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return {"status_code": resp.status_code}


__all__ = ["WorldServiceActivationClient"]
