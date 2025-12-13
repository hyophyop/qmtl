"""Helper to publish portfolio/risk snapshots into WorldService risk hub."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any, Mapping, cast

import httpx

from qmtl.foundation.common.hashutils import hash_bytes
from qmtl.services.worldservice.blob_store import BlobStore
from qmtl.services.risk_hub_contract import normalize_and_validate_snapshot


@dataclass
class RiskHubClient:
    """Lightweight client used by gateway/alloc paths to push snapshots into the hub."""

    base_url: str
    timeout: float = 5.0
    retries: int = 2
    backoff: float = 0.5
    auth_token: str | None = None
    client: httpx.AsyncClient | None = None
    blob_store: BlobStore | None = None
    inline_cov_threshold: int = 100
    actor: str = "gateway"
    stage: str | None = None
    ttl_sec: int = 10
    allowed_actors: Sequence[str] | None = None
    allowed_stages: Sequence[str] | None = None

    async def publish_snapshot(self, world_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """POST a snapshot to /risk-hub/worlds/{world_id}/snapshots."""

        payload = self._normalize_and_validate(world_id, payload)
        payload = self._maybe_offload_covariance(payload)
        payload = self._maybe_offload_auxiliary(payload)
        url = f"{self.base_url.rstrip('/')}/risk-hub/worlds/{world_id}/snapshots"
        close_client = False
        session = self.client
        if session is None:
            session = httpx.AsyncClient(timeout=self.timeout)
            close_client = True
        headers = {"Authorization": f"Bearer {self.auth_token}"} if self.auth_token else {}
        headers["X-Actor"] = self.actor
        if self.stage:
            headers["X-Stage"] = self.stage
        last_exc: Exception | None = None
        try:
            for attempt in range(self.retries + 1):
                try:
                    body = dict(payload)
                    body.setdefault("ttl_sec", self.ttl_sec)
                    resp = await session.post(url, json=body, headers=headers)
                    resp.raise_for_status()
                    return cast(dict[str, Any], resp.json())
                except Exception as exc:  # pragma: no cover - best-effort
                    last_exc = exc
                    if attempt >= self.retries:
                        break
                    await asyncio.sleep(self.backoff * (attempt + 1))
        finally:
            if close_client:
                try:
                    await session.aclose()
                except Exception:
                    pass
        if last_exc:
            raise last_exc
        raise RuntimeError("failed to publish snapshot")

    def _maybe_offload_covariance(self, payload: dict[str, Any]) -> dict[str, Any]:
        cov = payload.get("covariance")
        if not cov or not isinstance(cov, Mapping):
            return payload
        if self.blob_store is None or self.inline_cov_threshold is None:
            return payload
        if len(cov) <= self.inline_cov_threshold:
            return payload
        ref = self.blob_store.write(str(payload.get("version") or "cov"), cov)
        payload = dict(payload)
        payload["covariance_ref"] = ref
        payload.pop("covariance", None)
        return payload

    def _maybe_offload_auxiliary(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.blob_store is None or self.inline_cov_threshold is None:
            return payload
        version = str(payload.get("version") or "snapshot")

        # Realized returns time series: offload when inline payload is large.
        if payload.get("realized_returns_ref") is None and payload.get("realized_returns") is not None:
            realized = payload.get("realized_returns")
            data: Mapping[str, Any] | None = None
            if isinstance(realized, Mapping):
                data = realized
            else:
                series = realized if isinstance(realized, (list, tuple)) else None
                if series is not None:
                    data = {"returns": list(series)}
            if data is not None and (
                len(data) > self.inline_cov_threshold
                or any(isinstance(v, (list, tuple)) and len(v) > self.inline_cov_threshold for v in data.values())
            ):
                ref = self.blob_store.write(f"{version}-realized", data)
                payload = dict(payload)
                payload["realized_returns_ref"] = ref
                payload.pop("realized_returns", None)

        # Stress scenario results: optional offload.
        if payload.get("stress_ref") is None and payload.get("stress") is not None:
            stress = payload.get("stress")
            if isinstance(stress, Mapping) and len(stress) > self.inline_cov_threshold:
                ref = self.blob_store.write(f"{version}-stress", stress)
                payload = dict(payload)
                payload["stress_ref"] = ref
                payload.pop("stress", None)

        return payload

    def _normalize_and_validate(self, world_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return normalize_and_validate_snapshot(
                world_id,
                payload,
                actor=self.actor,
                stage=self.stage,
                ttl_sec_default=self.ttl_sec,
                allowed_actors=self.allowed_actors,
                allowed_stages=self.allowed_stages,
            )
        except TypeError:
            # Preserve legacy fallback only for non-JSON-serializable payloads.
            data: dict[str, Any] = dict(payload)
            data["world_id"] = world_id
            if not data.get("hash"):
                serialized = repr(sorted(data.items(), key=lambda kv: kv[0])).encode()
                data["hash"] = hash_bytes(serialized)
            return data

    async def publish_snapshot_sync(self, world_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Sync-friendly wrapper for contexts where async is unavailable."""

        return asyncio.get_event_loop().run_until_complete(
            self.publish_snapshot(world_id, payload)
        )


__all__ = ["RiskHubClient"]
