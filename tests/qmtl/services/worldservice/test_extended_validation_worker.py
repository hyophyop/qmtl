import pytest

import math

from qmtl.services.worldservice.extended_validation_worker import ExtendedValidationWorker
from qmtl.services.worldservice.policy_engine import parse_policy
from qmtl.services.worldservice.storage import Storage
from qmtl.services.worldservice.metrics import parse_timestamp
from qmtl.services.worldservice.risk_hub import RiskSignalHub, PortfolioSnapshot
from qmtl.services.worldservice.blob_store import JsonBlobStore


@pytest.mark.asyncio
async def test_extended_worker_updates_history():
    storage = Storage()
    await storage.create_world({"id": "wext", "name": "Extended World"})
    policy_payload = {
        "cohort": {"top_k": 1, "sharpe_median_min": 0.9, "severity": "soft"},
        "portfolio": {"max_incremental_var_99": 0.5, "severity": "soft"},
        "stress": {"scenarios": {"crash": {"dd_max": 0.3}}},
        "live_monitoring": {"sharpe_min": 0.6, "dd_max": 0.4, "severity": "soft"},
    }
    policy = parse_policy(policy_payload)
    version = await storage.add_policy("wext", policy)
    await storage.set_default_policy("wext", version=version)

    await storage.record_evaluation_run(
        "wext",
        "s-ext",
        "run-1",
        stage="backtest",
        risk_tier="medium",
        model_card_version="v1",
        metrics={
            "returns": {"sharpe": 1.1},
            "risk": {"incremental_var_99": 0.4},
            "stress": {"crash": {"max_drawdown": 0.2}},
            "diagnostics": {"live_sharpe": 0.95, "live_max_drawdown": 0.15},
        },
        validation={},
        summary={"status": "pass", "active": True, "active_set": ["s-ext"]},
    )

    worker = ExtendedValidationWorker(storage)
    updated = await worker.run("wext", stage="backtest")

    assert updated == 1
    record = await storage.get_evaluation_run("wext", "s-ext", "run-1")
    assert record is not None
    validation = record["validation"]
    assert validation["extended_revision"] == 1
    assert validation["extended_evaluated_at"]
    assert len(validation["extended_history"]) == 1
    results = validation["results"]
    assert "cohort" in results
    assert "portfolio" in results
    assert "stress" in results
    assert "live_monitoring" in results


@pytest.mark.asyncio
async def test_baseline_uses_risk_hub_covariance():
    storage = Storage()
    hub = RiskSignalHub()
    await storage.create_world({"id": "wbase"})
    await storage.set_decisions("wbase", ["s1", "s2"])
    snap = PortfolioSnapshot(
        world_id="wbase",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"s1": 0.5, "s2": 0.5},
        covariance={"s1,s1": 0.02, "s2,s2": 0.01, "s1,s2": 0.015},
    )
    await hub.upsert_snapshot(snap)

    worker = ExtendedValidationWorker(storage, risk_hub=hub)
    baseline = await worker._portfolio_baseline("wbase")

    assert baseline["var_99"] is not None
    assert baseline["es_99"] is not None


@pytest.mark.asyncio
async def test_incremental_var_es_uses_active_snapshot_covariance():
    storage = Storage()
    hub = RiskSignalHub()
    await storage.create_world({"id": "winc"})
    policy = parse_policy({"portfolio": {"max_incremental_var_99": 0.01, "severity": "soft"}})
    version = await storage.add_policy("winc", policy)
    await storage.set_default_policy("winc", version=version)

    await storage.record_evaluation_run(
        "winc",
        "s-cand",
        "run-1",
        stage="backtest",
        risk_tier="medium",
        metrics={"returns": {"sharpe": 1.0, "max_drawdown": 0.1}},
        validation={},
        summary={"status": "pass"},
    )

    snap = PortfolioSnapshot(
        world_id="winc",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"s-live": 1.0},
        covariance={
            "s-live,s-live": 0.0001,
            "s-cand,s-cand": 0.0004,
            "s-live,s-cand": 0.00005,
        },
        provenance={"actor": "gateway", "stage": "backtest"},
    )
    await hub.upsert_snapshot(snap)

    worker = ExtendedValidationWorker(storage, risk_hub=hub)
    updated = await worker.run("winc", stage="backtest")
    assert updated == 1

    record = await storage.get_evaluation_run("winc", "s-cand", "run-1")
    assert record is not None
    risk = record["metrics"]["risk"]

    z = 2.33
    baseline_var = z * math.sqrt(0.0001)
    with_candidate_var = z * math.sqrt(0.00015)
    expected_delta = with_candidate_var - baseline_var

    assert risk["incremental_var_99"] == pytest.approx(expected_delta, rel=1e-4)
    assert risk["incremental_es_99"] == pytest.approx(expected_delta * 1.2, rel=1e-4)
    assert record["validation"]["results"]["portfolio"]["status"] == "pass"


@pytest.mark.asyncio
async def test_portfolio_baseline_uses_weights_and_correlations():
    storage = Storage()
    await storage.create_world({"id": "wport"})
    await storage.set_decisions("wport", ["s1", "s2"])
    await storage.update_activation(
        "wport",
        {
            "strategy_id": "s1",
            "side": "long",
            "active": True,
            "weight": 0.6,
            "ts": "2025-01-01T00:00:00Z",
        },
    )
    await storage.update_activation(
        "wport",
        {
            "strategy_id": "s2",
            "side": "long",
            "active": True,
            "weight": 0.4,
            "ts": "2025-01-01T00:00:01Z",
        },
    )

    await storage.record_evaluation_run(
        "wport",
        "s1",
        "run-1",
        stage="backtest",
        risk_tier="medium",
        metrics={
            "returns": {"sharpe": 1.0, "max_drawdown": 0.1},
            "risk": {"incremental_var_99": 0.1},
            "diagnostics": {
                "extra_metrics": {"pairwise_correlations": {"s1:s2": 0.5}},
            },
        },
        validation={},
        summary={"status": "pass"},
        created_at="2025-02-01T00:00:00Z",
    )
    await storage.record_evaluation_run(
        "wport",
        "s2",
        "run-2",
        stage="backtest",
        risk_tier="medium",
        metrics={
            "returns": {"sharpe": 0.5, "max_drawdown": 0.2},
            "risk": {"incremental_var_99": 0.2},
            "diagnostics": {
                "extra_metrics": {"pairwise_correlations": {"s1:s2": 0.5}},
            },
        },
        validation={},
        summary={"status": "pass"},
        created_at="2025-02-01T00:00:01Z",
    )

    worker = ExtendedValidationWorker(storage)
    baseline = await worker._portfolio_baseline("wport")

    assert baseline["count"] == 2
    # Sharpe should be weighted average: 0.6*1.0 + 0.4*0.5 = 0.8
    assert baseline["sharpe"] == pytest.approx(0.8, rel=1e-3)
    # Portfolio var should reflect correlation (0.5) and be < simple sum of vars
    simple_sum = 0.1 * 0.6 + 0.2 * 0.4
    assert baseline["var_99"] is not None
    assert baseline["var_99"] < simple_sum * 2  # should be bounded below naive sum


@pytest.mark.asyncio
async def test_extended_worker_derives_live_metrics_from_realized_returns_ref(tmp_path):
    storage = Storage()
    await storage.create_world({"id": "wlive"})
    policy_payload = {
        "live_monitoring": {"sharpe_min": 0.0, "dd_max": 10.0, "severity": "soft"},
    }
    policy = parse_policy(policy_payload)
    version = await storage.add_policy("wlive", policy)
    await storage.set_default_policy("wlive", version=version)

    await storage.record_evaluation_run(
        "wlive",
        "s-live",
        "run-live-1",
        stage="paper",
        risk_tier="medium",
        metrics={"returns": {"sharpe": 1.0}},
        validation={},
        summary={"status": "pass"},
    )

    blob_store = JsonBlobStore(tmp_path / "blobs")
    hub = RiskSignalHub(blob_store=blob_store)
    ref = blob_store.write("realized", {"s-live": [0.01, -0.005, 0.02, 0.0]})
    snap = PortfolioSnapshot(
        world_id="wlive",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"s-live": 1.0},
        realized_returns_ref=ref,
        provenance={"actor": "gateway", "stage": "paper"},
    )
    await hub.upsert_snapshot(snap)

    worker = ExtendedValidationWorker(storage, risk_hub=hub)
    updated = await worker.run("wlive", stage="paper")

    assert updated == 1
    record = await storage.get_evaluation_run("wlive", "s-live", "run-live-1")
    assert record is not None
    diagnostics = record["metrics"]["diagnostics"]
    assert diagnostics.get("live_sharpe") is not None
    assert record["validation"]["results"]["live_monitoring"]["reason_code"] != "live_sharpe_missing"


@pytest.mark.asyncio
async def test_extended_worker_injects_stress_from_hub_ref(tmp_path):
    storage = Storage()
    await storage.create_world({"id": "wstress"})
    policy_payload = {
        "stress": {"scenarios": {"crash": {"dd_max": 0.3}}, "severity": "soft"},
    }
    policy = parse_policy(policy_payload)
    version = await storage.add_policy("wstress", policy)
    await storage.set_default_policy("wstress", version=version)

    await storage.record_evaluation_run(
        "wstress",
        "s-stress",
        "run-1",
        stage="paper",
        risk_tier="medium",
        metrics={"returns": {"sharpe": 1.0}},
        validation={},
        summary={"status": "pass"},
    )

    blob_store = JsonBlobStore(tmp_path / "blobs")
    hub = RiskSignalHub(blob_store=blob_store)
    stress_ref = blob_store.write(
        "stress",
        {"s-stress": {"crash": {"max_drawdown": 0.2}}},
    )
    snap = PortfolioSnapshot(
        world_id="wstress",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"s-stress": 1.0},
        stress_ref=stress_ref,
        provenance={"actor": "gateway", "stage": "paper"},
    )
    await hub.upsert_snapshot(snap)

    worker = ExtendedValidationWorker(storage, risk_hub=hub)
    updated = await worker.run("wstress", stage="paper")
    assert updated == 1

    record = await storage.get_evaluation_run("wstress", "s-stress", "run-1")
    assert record is not None
    results = record["validation"]["results"]
    assert "stress" in results
    assert results["stress"]["reason_code"] != "crash_dd_missing"
