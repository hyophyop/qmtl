import time
import warnings

import pytest
from fastapi.testclient import TestClient

from qmtl.services.gateway.api import create_app, Database
from qmtl.services.gateway.models import StrategySubmit
from qmtl.foundation.common import crc32_of_list
from qmtl.services.gateway import metrics

warnings.filterwarnings(
    "ignore", category=ResourceWarning, message="unclosed event loop"
)

class FakeDB(Database):
    async def insert_strategy(self, strategy_id: str, meta):
        pass

    async def set_status(self, strategy_id: str, status: str):
        pass

    async def get_status(self, strategy_id: str):
        return "queued"

    async def append_event(self, strategy_id: str, event: str):
        pass


@pytest.fixture
def app(fake_redis):
    db = FakeDB()
    return create_app(redis_client=fake_redis, database=db, enable_background=False)


def test_metrics_endpoint(app):
    metrics.reset_metrics()
    metrics.lost_requests_total.inc()
    metrics.observe_gateway_latency(42)
    metrics.record_sentinel_weight_update("v1")
    metrics.set_sentinel_traffic_ratio("v1", 0.5)
    with TestClient(app) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "lost_requests_total" in resp.text
        assert "gateway_e2e_latency_p95" in resp.text
        assert "gateway_sentinel_traffic_ratio" in resp.text
        assert "sentinel_skew_seconds" in resp.text
        resp.close()


def test_latency_metric_recorded(app):
    metrics.reset_metrics()
    with TestClient(app, raise_server_exceptions=False) as client:
        payload = StrategySubmit(
            dag_json="{}",
            meta=None,
            node_ids_crc32=crc32_of_list([]),
        )
        client.post("/strategies", json=payload.model_dump())
        assert metrics.gateway_e2e_latency_p95._value.get() > 0


def test_lost_requests_counter(monkeypatch, fake_redis):
    metrics.reset_metrics()
    redis = fake_redis
    async def fail(*args, **kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(redis, "rpush", fail)
    db = FakeDB()
    app = create_app(redis_client=redis, database=db, enable_background=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        payload = StrategySubmit(
            dag_json="{}",
            meta=None,
            node_ids_crc32=crc32_of_list([]),
        )
        resp = client.post("/strategies", json=payload.model_dump())
        assert resp.status_code == 500
        assert metrics.lost_requests_total._value.get() == 1
