import httpx
import pytest

from qmtl.foundation.common.metrics_factory import get_metric_value
from qmtl.services.worldservice.api import create_app
from qmtl.services.worldservice.blob_store import JsonBlobStore
from qmtl.services.worldservice import metrics as ws_metrics
from qmtl.services.worldservice.risk_hub import PortfolioSnapshot, RiskSignalHub
from qmtl.services.worldservice.storage import Storage


@pytest.mark.asyncio
async def test_live_monitoring_run_endpoint_materializes_runs(tmp_path):
    ws_metrics.reset_metrics()
    store = Storage()
    blob_store = JsonBlobStore(tmp_path / "blobs")
    hub = RiskSignalHub(blob_store=blob_store)
    ref = blob_store.write("realized", {"s1": [0.01, -0.005, 0.02, 0.0]})
    await hub.upsert_snapshot(
        PortfolioSnapshot(
            world_id="wrun",
            as_of="2025-01-01T00:00:00Z",
            version="v1",
            weights={"s1": 1.0},
            realized_returns_ref=ref,
            provenance={"actor": "gateway", "stage": "live"},
        )
    )

    app = create_app(storage=store, risk_hub=hub)

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wrun", "name": "Run World"})
            await client.post(
                "/worlds/wrun/policies",
                json={"policy": {"live_monitoring": {"sharpe_min": 0.0, "dd_max": 10.0}}},
            )
            await client.post("/worlds/wrun/set-default", json={"version": 1})

            resp = await client.post("/worlds/wrun/live-monitoring/run")
            assert resp.status_code == 200
            assert resp.json()["updated"] == 1

            report_resp = await client.get("/worlds/wrun/live-monitoring/report")
            assert report_resp.status_code == 200
            body = report_resp.json()
            assert any(item["strategy_id"] == "s1" for item in body["strategies"])

    assert (
        get_metric_value(
            ws_metrics.live_monitoring_run_total,
            {"world_id": "wrun", "status": "success"},
        )
        == 1.0
    )
    assert (
        get_metric_value(
            ws_metrics.live_monitoring_run_updated_strategies_total,
            {"world_id": "wrun"},
        )
        == 1.0
    )
