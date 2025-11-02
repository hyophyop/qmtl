from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

import httpx

from . import metrics as sdk_metrics
from . import runtime

logger = logging.getLogger(__name__)
_WORKER_ID_ENV_VARS: tuple[str, ...] = (
    "QMTL_SEAMLESS_WORKER",
    "QMTL_WORKER_ID",
    "HOSTNAME",
)


def _connectors_worker_ids() -> tuple[str, ...]:
    spec = importlib.util.find_spec("qmtl.runtime.sdk.configuration")
    if spec is None:
        return ()

    cfg = None
    try:
        configuration = importlib.import_module("qmtl.runtime.sdk.configuration")
        get_connectors_config = getattr(configuration, "get_connectors_config", None)
        if callable(get_connectors_config):
            cfg = get_connectors_config()
    except Exception:  # pragma: no cover - defensive cache access
        return ()

    values: list[str] = []
    for attr in ("seamless_worker_id", "worker_id"):
        value = getattr(cfg, attr, None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            values.append(text)
    return tuple(values)


def _maybe_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_worker_id() -> str | None:
    for candidate in _connectors_worker_ids():
        if candidate:
            return candidate

    for env in _WORKER_ID_ENV_VARS:
        candidate = os.getenv(env, "").strip()
        if candidate:
            return candidate
    return None


def _build_log_extra(
    key: str,
    *,
    lease: Lease | None,
    coordinator_id: str,
    worker_id: str | None,
    completion_ratio: Any = None,
    reason: str | None = None,
) -> dict[str, Any]:
    parts = key.split(":", 5)
    node_id = parts[0] if parts and parts[0] else "unknown"
    interval = parts[1] if len(parts) > 1 and parts[1] else None
    batch_start = parts[2] if len(parts) > 2 else None
    batch_end = parts[3] if len(parts) > 3 else None
    world = parts[4] if len(parts) > 4 and parts[4] else None
    requested_as_of = parts[5] if len(parts) > 5 and parts[5] else None

    extra: dict[str, Any] = {
        "coordinator_id": coordinator_id,
        "lease_key": key,
        "node_id": node_id,
        "interval": _maybe_int(interval) if interval and interval.isdigit() else interval,
        "batch_start": _maybe_int(batch_start),
        "batch_end": _maybe_int(batch_end),
        "world": world,
        "requested_as_of": requested_as_of,
    }

    if worker_id:
        extra["worker"] = worker_id

    if lease is not None:
        extra["lease_token"] = lease.token
        extra["lease_until_ms"] = lease.lease_until_ms

    ratio = _maybe_float(completion_ratio)
    if ratio is not None:
        extra["completion_ratio"] = ratio

    if reason is not None:
        extra["reason"] = reason

    return extra


@dataclass
class Lease:
    key: str
    token: str
    lease_until_ms: int


class BackfillCoordinator(Protocol):
    async def claim(self, key: str, lease_ms: int) -> Lease | None: ...
    async def complete(self, lease: Lease) -> None: ...
    async def fail(self, lease: Lease, reason: str) -> None: ...


def _label_tuple_from_key(key: str) -> tuple[str, str, str]:
    """Derive metric labels from a coordinator lease key."""

    parts = key.split(":", 2)
    node_id = parts[0] if parts and parts[0] else "unknown"
    interval = parts[1] if len(parts) > 1 and parts[1] else "unknown"
    return node_id, interval, key


class InMemoryBackfillCoordinator:
    """Process-local single-flight guard for background backfills.

    Not distributed; intended as a drop-in to prevent duplicate in-process
    backfills while the distributed coordinator is being integrated.
    """

    def __init__(self) -> None:
        self._leases: dict[str, Lease] = {}

    async def claim(self, key: str, lease_ms: int) -> Lease | None:
        now = int(time.time() * 1000)
        lease = self._leases.get(key)
        if lease and lease.lease_until_ms > now:
            return None
        new = Lease(key=key, token=f"{now:x}", lease_until_ms=now + int(lease_ms))
        self._leases[key] = new
        return new

    async def complete(self, lease: Lease) -> None:
        cur = self._leases.get(lease.key)
        if cur and cur.token == lease.token:
            self._leases.pop(lease.key, None)

    async def fail(self, lease: Lease, reason: str) -> None:  # pragma: no cover - trivial
        await self.complete(lease)


class DistributedBackfillCoordinator:
    """HTTP client for the distributed Seamless backfill coordinator."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        url = (base_url or "").strip()
        if not url:
            raise ValueError("DistributedBackfillCoordinator requires a base URL")
        self._base_url = url.rstrip("/")
        parsed = urlparse(self._base_url)
        coordinator_id = parsed.netloc or parsed.path or self._base_url
        self._coordinator_id = coordinator_id
        self._worker_id = _resolve_worker_id()
        self._client_factory = client_factory or self._default_client_factory

    def _default_client_factory(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS)

    async def _post(self, path: str, payload: dict) -> httpx.Response:
        client = self._client_factory()
        async with client:
            return await client.post(f"{self._base_url}{path}", json=payload)

    def _record_completion(self, key: str, ratio: float | None) -> None:
        if ratio is None:
            return
        node_id, interval, lease_key = _label_tuple_from_key(key)
        sdk_metrics.observe_backfill_completion_ratio(
            node_id=node_id,
            interval=interval,
            lease_key=lease_key,
            ratio=ratio,
        )

    async def claim(self, key: str, lease_ms: int) -> Lease | None:
        payload = {"key": key, "lease_ms": lease_ms}
        try:
            response = await self._post("/v1/leases/claim", payload)
        except httpx.RequestError as exc:
            logger.warning("seamless.coordinator.claim_failed", exc_info=exc)
            return None

        if response.status_code in {404, 409}:
            return None

        try:
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("seamless.coordinator.bad_claim_response", exc_info=exc)
            return None

        lease_data = data.get("lease") or {}
        token = lease_data.get("token")
        lease_until = lease_data.get("lease_until_ms")
        if not token or lease_until is None:
            return None

        lease = Lease(key=key, token=str(token), lease_until_ms=int(lease_until))
        self._record_completion(key, data.get("completion_ratio"))
        logger.info(
            "seamless.backfill.coordinator_claimed",
            extra=_build_log_extra(
                key,
                lease=lease,
                coordinator_id=self._coordinator_id,
                worker_id=self._worker_id,
                completion_ratio=data.get("completion_ratio"),
            ),
        )
        return lease

    async def complete(self, lease: Lease) -> None:
        payload = {"key": lease.key, "token": lease.token}
        try:
            response = await self._post("/v1/leases/complete", payload)
        except httpx.RequestError as exc:
            logger.warning("seamless.coordinator.complete_failed", exc_info=exc)
            return

        if response.status_code >= 400 and response.status_code not in {404, 409}:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover - unlikely
                logger.warning("seamless.coordinator.complete_status_error", exc_info=exc)
                return

        try:
            data = response.json()
        except Exception:  # pragma: no cover - defensive
            data = {}

        completion_ratio = data.get("completion_ratio", 1.0)
        self._record_completion(lease.key, completion_ratio)
        if response.status_code < 400:
            logger.info(
                "seamless.backfill.coordinator_completed",
                extra=_build_log_extra(
                    lease.key,
                    lease=lease,
                    coordinator_id=self._coordinator_id,
                    worker_id=self._worker_id,
                    completion_ratio=completion_ratio,
                ),
            )

    async def fail(self, lease: Lease, reason: str) -> None:
        payload = {"key": lease.key, "token": lease.token, "reason": reason}
        try:
            response = await self._post("/v1/leases/fail", payload)
        except httpx.RequestError as exc:
            logger.warning("seamless.coordinator.fail_failed", exc_info=exc)
            return

        if response.status_code >= 400 and response.status_code not in {404, 409}:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover - unlikely
                logger.warning("seamless.coordinator.fail_status_error", exc_info=exc)
                return

        try:
            data = response.json()
        except Exception:  # pragma: no cover - defensive
            data = {}

        completion_ratio = data.get("completion_ratio", 0.0)
        self._record_completion(lease.key, completion_ratio)
        if response.status_code < 400:
            logger.info(
                "seamless.backfill.coordinator_failed",
                extra=_build_log_extra(
                    lease.key,
                    lease=lease,
                    coordinator_id=self._coordinator_id,
                    worker_id=self._worker_id,
                    completion_ratio=completion_ratio,
                    reason=reason,
                ),
            )


__all__ = [
    "BackfillCoordinator",
    "DistributedBackfillCoordinator",
    "InMemoryBackfillCoordinator",
    "Lease",
]
