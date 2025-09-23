import pytest

from qmtl.services.gateway.database import PostgresDatabase
from qmtl.services.gateway.ownership import OwnershipManager
from qmtl.services.gateway import metrics as gw_metrics


class _Conn:
    async def fetchval(self, query: str, key: int) -> bool:
        return True


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, exc_type, exc, tb):
                return None

        return _Ctx()


class _KafkaOwner:
    def __init__(self):
        self.calls: list[int] = []

    async def acquire(self, key: int) -> bool:
        self.calls.append(key)
        return True

    async def release(self, key: int) -> None:  # pragma: no cover - not used
        return None


@pytest.mark.asyncio
async def test_ownership_handoff_metric_increments_on_owner_change():
    gw_metrics.reset_metrics()
    db = PostgresDatabase("dsn")
    db._pool = _Pool(_Conn())  # type: ignore[assignment]
    kafka = _KafkaOwner()
    mgr = OwnershipManager(db, kafka)

    # First owner acquires key
    assert await mgr.acquire(123, owner="w1")
    # Different owner acquires same key -> increment handoff metric
    assert await mgr.acquire(123, owner="w2")
    assert gw_metrics.owner_reassign_total._value.get() >= 1

