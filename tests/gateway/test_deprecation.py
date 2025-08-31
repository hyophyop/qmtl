from fastapi.testclient import TestClient
from typing import List, AsyncGenerator

from qmtl.gateway.api import create_app, Database
from qmtl.sdk.node import MatchMode


class FakeWatchHub:
    """Mock watch hub that doesn't hang for testing."""
    
    async def subscribe(
        self, tags: List[str], interval: int, match_mode: MatchMode
    ) -> AsyncGenerator[List[str], None]:
        """Return empty generator that terminates immediately."""
        # Return once with empty list and then terminate
        yield []
        return
    
    async def broadcast(self, *args, **kwargs):
        """No-op broadcast."""
        pass


class FakeDB(Database):
    async def insert_strategy(self, strategy_id: str, meta):  # pragma: no cover - unused
        pass

    async def set_status(self, strategy_id: str, status: str):  # pragma: no cover - unused
        pass

    async def get_status(self, strategy_id: str):  # pragma: no cover - unused
        return "queued"

    async def append_event(self, strategy_id: str, event: str):  # pragma: no cover - unused
        pass


def test_queues_watch_has_deprecation_headers(fake_redis):
    app = create_app(redis_client=fake_redis, database=FakeDB(), watch_hub=FakeWatchHub())
    with TestClient(app) as client:
        resp = client.get("/queues/watch", params={"tags": "t1", "interval": 60})
        # Streaming response still carries headers
        assert resp.headers.get("Deprecation") == "true"
        assert "/events/subscribe" in (resp.headers.get("Link") or "")
        resp.close()

