import pytest

from qmtl.services.worldservice.blob_store import JsonBlobStore
from qmtl.services.worldservice.risk_hub import RiskSignalHub, PortfolioSnapshot


@pytest.mark.asyncio
async def test_covariance_offloaded_to_blob_store(tmp_path):
    store = JsonBlobStore(tmp_path / "blobs")
    hub = RiskSignalHub(blob_store=store, inline_cov_threshold=1)
    snap = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 1.0},
        covariance={"a,a": 0.1, "a,b": 0.2},
    )
    await hub.upsert_snapshot(snap)

    latest = await hub.latest_snapshot("w")
    assert latest is not None
    # Covariance is offloaded and then materialized back via blob store resolver
    assert latest.covariance_ref is not None
    assert latest.covariance is not None

    # When reloaded, covariance should materialize from blob store
    hub.bind_covariance_resolver(store.read)
    materialized = await hub.latest_snapshot("w")
    assert materialized.covariance is not None
