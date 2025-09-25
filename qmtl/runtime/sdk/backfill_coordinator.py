from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import time


@dataclass
class Lease:
    key: str
    token: str
    lease_until_ms: int


class BackfillCoordinator(Protocol):
    async def claim(self, key: str, lease_ms: int) -> Lease | None: ...
    async def complete(self, lease: Lease) -> None: ...
    async def fail(self, lease: Lease, reason: str) -> None: ...


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


__all__ = ["BackfillCoordinator", "InMemoryBackfillCoordinator", "Lease"]

