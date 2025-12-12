import pytest

from qmtl.services.worldservice.extended_validation_worker import ExtendedValidationWorker
from qmtl.services.worldservice.policy_engine import parse_policy
from qmtl.services.worldservice.storage import Storage
from qmtl.services.worldservice.risk_hub import RiskSignalHub, PortfolioSnapshot
from qmtl.services.worldservice.blob_store import JsonBlobStore


@pytest.mark.asyncio
async def test_baseline_uses_covariance_resolver():
    storage = Storage()
    await storage.create_world({"id": "wcov"})
    await storage.set_decisions("wcov", ["s1", "s2"])

    async def _resolve_cov(ref: str):
        return {"s1,s1": 0.02, "s2,s2": 0.01, "s1,s2": 0.015} if ref == "cov://v1" else {}

    hub = RiskSignalHub(covariance_resolver=_resolve_cov)
    snap = PortfolioSnapshot(
        world_id="wcov",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"s1": 0.5, "s2": 0.5},
        covariance_ref="cov://v1",
    )
    await hub.upsert_snapshot(snap)

    policy = parse_policy({"cohort": {"top_k": 1}})
    version = await storage.add_policy("wcov", policy)
    await storage.set_default_policy("wcov", version=version)
    await storage.record_evaluation_run(
        "wcov",
        "s1",
        "r1",
        stage="backtest",
        risk_tier="medium",
        metrics={"returns": {"sharpe": 1.0}},
        validation={},
        summary={"status": "pass"},
    )

    worker = ExtendedValidationWorker(storage, risk_hub=hub)
    baseline = await worker._portfolio_baseline("wcov")
    assert baseline["var_99"] is not None
    assert baseline["es_99"] is not None


@pytest.mark.asyncio
async def test_worker_handles_many_runs_and_offloaded_covariance(tmp_path):
    storage = Storage()
    await storage.create_world({"id": "wload"})
    policy = parse_policy({"cohort": {"top_k": 5}})
    version = await storage.add_policy("wload", policy)
    await storage.set_default_policy("wload", version=version)

    # Seed many runs
    strategies = [f"s{i}" for i in range(20)]
    for sid in strategies:
        await storage.record_evaluation_run(
            "wload",
            sid,
            f"run-{sid}",
            stage="backtest",
            risk_tier="medium",
            metrics={"returns": {"sharpe": 1.0}},
            validation={},
            summary={"status": "pass"},
        )

    # Offloaded covariance snapshot
    weights = {sid: 1.0 / len(strategies) for sid in strategies}
    cov = {f"{sid},{sid}": 0.02 for sid in strategies}
    blob_store = JsonBlobStore(tmp_path / "cov_blobs")
    hub = RiskSignalHub(blob_store=blob_store, inline_cov_threshold=5)
    snap = PortfolioSnapshot(
        world_id="wload",
        as_of="2025-01-01T00:00:00Z",
        version="v-large",
        weights=weights,
        covariance=cov,
    )
    await hub.upsert_snapshot(snap)

    worker = ExtendedValidationWorker(storage, risk_hub=hub)
    updated = await worker.run("wload", stage="backtest")
    assert updated == len(strategies)
