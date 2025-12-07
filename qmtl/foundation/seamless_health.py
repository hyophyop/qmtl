from __future__ import annotations

import asyncio
import time
from typing import Iterable

from qmtl.foundation.common.health import (
    CheckResult,
    probe_http,
    probe_http_async,
)

HEALTH_ENDPOINT = "/healthz"
SERVICE_NAME = "seamless-coordinator"


def _health_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}{HEALTH_ENDPOINT}"


def _format_probe_details(result: CheckResult) -> str:
    parts: list[str] = [f"code={result.code}"]
    if result.status is not None:
        parts.append(f"status={result.status}")
    if result.err:
        parts.append(f"error={result.err}")
    if result.latency_ms is not None:
        parts.append(f"latency_ms={result.latency_ms:.1f}")
    return ", ".join(parts) if parts else "no additional detail"


def format_coordinator_probe(result: CheckResult) -> str:
    """Return a human-friendly description of a coordinator health probe."""

    return _format_probe_details(result)


async def probe_coordinator_health_async(
    base_url: str,
    *,
    attempts: int = 3,
    backoff_seconds: float = 10.0,
    timeout_seconds: float = 5.0,
) -> CheckResult:
    """Probe the coordinator health endpoint with limited retries."""

    url = _health_url(base_url)
    last: CheckResult | None = None
    for remaining in range(attempts, 0, -1):
        result = await probe_http_async(
            url,
            service=SERVICE_NAME,
            endpoint=HEALTH_ENDPOINT,
            timeout=timeout_seconds,
        )
        last = result
        if result.ok or remaining == 1:
            return result
        await asyncio.sleep(backoff_seconds)
    assert last is not None  # defensive: loop always sets last
    return last


def probe_coordinator_health(
    base_url: str,
    *,
    attempts: int = 3,
    backoff_seconds: float = 10.0,
    timeout_seconds: float = 5.0,
) -> CheckResult:
    """Synchronous variant of :func:`probe_coordinator_health_async`."""

    url = _health_url(base_url)
    last: CheckResult | None = None
    for remaining in range(attempts, 0, -1):
        result = probe_http(
            url,
            service=SERVICE_NAME,
            endpoint=HEALTH_ENDPOINT,
            timeout=timeout_seconds,
        )
        last = result
        if result.ok or remaining == 1:
            return result
        time.sleep(backoff_seconds)
    assert last is not None  # defensive: loop always sets last
    return last


__all__: Iterable[str] = [
    "format_coordinator_probe",
    "probe_coordinator_health",
    "probe_coordinator_health_async",
]
