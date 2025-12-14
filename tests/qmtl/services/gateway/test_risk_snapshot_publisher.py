import pytest

from qmtl.services.gateway.risk_hub_client import RiskHubClient
from qmtl.services.worldservice.blob_store import JsonBlobStore


class _StubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url: str, json: dict, headers=None):
        self.calls.append((url, json, headers))

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": True}

        return _Resp()

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_risk_hub_client_offloads_covariance(tmp_path):
    blob = JsonBlobStore(tmp_path / "blobs")
    client = _StubClient()
    hub = RiskHubClient(
        base_url="http://hub",
        client=client,
        retries=0,
        blob_store=blob,
        inline_cov_threshold=1,
        actor="gateway",
        stage="paper",
    )
    await hub.publish_snapshot(
        "w",
        {
            "version": "v1",
            "as_of": "2025-01-01T00:00:00Z",
            "weights": {"a": 1.0},
            "covariance": {"a,a": 0.1, "a,b": 0.2},
        },
    )
    assert client.calls
    _, payload, _ = client.calls[0]
    assert "covariance" not in payload
    assert payload.get("covariance_ref", "").startswith("file://")
