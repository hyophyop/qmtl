import pytest
from types import SimpleNamespace
from fastapi import FastAPI
import httpx

from qmtl.common import compute_node_id
from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.gateway.event_handlers import create_event_router
from qmtl.gateway.event_descriptor import EventDescriptorConfig, validate_event_token
from qmtl.sdk.activation_manager import ActivationManager
from qmtl.common.cloudevents import EVENT_SCHEMA_VERSION
from qmtl.sdk.metrics import node_processed_total, generate_latest, global_registry


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
@pytest.mark.asyncio
async def test_world_isolation(monkeypatch):
    # 동일 전략 노드가 world에 관계없이 동일한 ID를 갖는다
    base = ("T", "code", "cfg", "schema")
    nid1 = compute_node_id(*base)
    nid2 = compute_node_id(*base)
    assert nid1 == nid2

    # world별 구독 토픽이 분리된다
    client = DagManagerClient("dummy")

    class StubTagStub:
        async def GetQueues(self, request):
            return SimpleNamespace(queues=[SimpleNamespace(**{"queue": "base", "global": False})])

    def fake_ensure(self):
        self._tag_stub = StubTagStub()

    monkeypatch.setattr(DagManagerClient, "_ensure_channel", fake_ensure)
    q1 = await client.get_queues_by_tag(["t"], 60, world_id="w1")
    q2 = await client.get_queues_by_tag(["t"], 60, world_id="w2")
    assert q1[0]["queue"] == "w/w1/base"
    assert q2[0]["queue"] == "w/w2/base"
    await client.close()

    # 활성 이벤트가 세계마다 독립적으로 처리된다
    am1 = ActivationManager(world_id="w1", strategy_id="s1")
    am2 = ActivationManager(world_id="w2", strategy_id="s1")
    await am1._on_message(
        {
            "event": "activation_updated",
            "data": {"side": "long", "active": True, "version": EVENT_SCHEMA_VERSION},
        }
    )
    await am2._on_message(
        {
            "event": "activation_updated",
            "data": {"side": "long", "active": False, "version": EVENT_SCHEMA_VERSION},
        }
    )
    assert am1.allow_side("long") is True
    assert am2.allow_side("long") is False
    await am1.stop()
    await am2.stop()

    # 메트릭은 동일한 node_id에 집계된다
    node_processed_total.clear()
    node_processed_total.labels(node_id=nid1).inc()
    node_processed_total.labels(node_id=nid2).inc()
    metrics_text = generate_latest(global_registry).decode()
    assert f'node_processed_total{{node_id="{nid1}"}} 2.0' in metrics_text

    # /events/subscribe 응답에 world 스코프가 포함된다
    cfg = EventDescriptorConfig(keys={"a": "secret"}, active_kid="a")
    router = create_event_router(None, cfg)
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        for wid in ("w1", "w2"):
            resp = await ac.post(
                "/events/subscribe",
                json={"world_id": wid, "strategy_id": "s1", "topics": ["activation"]},
            )
            assert resp.status_code == 200
            token = resp.json()["token"]
            claims = validate_event_token(token, cfg)
            assert claims["world_id"] == wid
    await transport.aclose()
