import pytest

from qmtl.services.worldservice.live_monitoring_worker import LiveMonitoringWorker
from qmtl.services.worldservice.policy_engine import parse_policy
from qmtl.services.worldservice.risk_hub import RiskSignalHub, PortfolioSnapshot
from qmtl.services.worldservice.storage import Storage
from qmtl.services.worldservice.blob_store import JsonBlobStore


@pytest.mark.asyncio
async def test_live_monitoring_worker_creates_live_runs_and_evaluates(tmp_path):
    storage = Storage()
    await storage.create_world({"id": "wlive", "name": "Live World"})
    policy = parse_policy({"live_monitoring": {"sharpe_min": 0.0, "dd_max": 10.0}})
    version = await storage.add_policy("wlive", policy)
    await storage.set_default_policy("wlive", version=version)

    await storage.set_decisions("wlive", ["s1"])
    await storage.record_evaluation_run(
        "wlive",
        "s1",
        "run-backtest",
        stage="paper",
        risk_tier="medium",
        metrics={"returns": {"sharpe": 1.0}},
        summary={"status": "pass"},
    )

    blob_store = JsonBlobStore(tmp_path / "blobs")
    hub = RiskSignalHub(blob_store=blob_store)
    ref = blob_store.write("realized", {"s1": [0.01, -0.005, 0.02, 0.0]})
    snap = PortfolioSnapshot(
        world_id="wlive",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"s1": 1.0},
        realized_returns_ref=ref,
        provenance={"actor": "gateway", "stage": "live"},
    )
    await hub.upsert_snapshot(snap)

    worker = LiveMonitoringWorker(storage, risk_hub=hub)
    updated = await worker.run_world("wlive")
    assert updated == 1

    runs = await storage.list_evaluation_runs(world_id="wlive", strategy_id="s1")
    live_runs = [r for r in runs if r.get("stage") == "live"]
    assert len(live_runs) == 1
    diagnostics = live_runs[0]["metrics"]["diagnostics"]
    assert diagnostics.get("live_sharpe") is not None
    assert "live_monitoring" in (live_runs[0]["validation"].get("results") or {})


@pytest.mark.asyncio
async def test_live_monitoring_worker_respects_windows(tmp_path):
    storage = Storage()
    await storage.create_world({"id": "wlive", "name": "Live World"})
    policy = parse_policy({"live_monitoring": {"sharpe_min": 0.0, "dd_max": 10.0}})
    version = await storage.add_policy("wlive", policy)
    await storage.set_default_policy("wlive", version=version)

    await storage.set_decisions("wlive", ["s1"])
    await storage.record_evaluation_run(
        "wlive",
        "s1",
        "run-backtest",
        stage="paper",
        risk_tier="medium",
        metrics={"returns": {"sharpe": 1.0}},
        summary={"status": "pass"},
    )

    blob_store = JsonBlobStore(tmp_path / "blobs")
    hub = RiskSignalHub(blob_store=blob_store)
    ref = blob_store.write("realized", {"s1": [0.01, -0.005, 0.02, 0.0]})
    snap = PortfolioSnapshot(
        world_id="wlive",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"s1": 1.0},
        realized_returns_ref=ref,
        provenance={"actor": "gateway", "stage": "live"},
    )
    await hub.upsert_snapshot(snap)

    worker = LiveMonitoringWorker(storage, risk_hub=hub, windows=(2,))
    updated = await worker.run_world("wlive")
    assert updated == 1

    runs = await storage.list_evaluation_runs(world_id="wlive", strategy_id="s1")
    live_runs = [r for r in runs if r.get("stage") == "live"]
    assert len(live_runs) == 1
    diagnostics = live_runs[0]["metrics"].get("diagnostics") or {}

    assert "live_sharpe_p2" in diagnostics
    assert diagnostics.get("live_sharpe") == diagnostics.get("live_sharpe_p2")
    assert "live_sharpe_p30" not in diagnostics
