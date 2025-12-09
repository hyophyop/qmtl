import httpx
import pytest

from qmtl.services.worldservice.api import create_app
from qmtl.services.worldservice.storage import Storage


@pytest.mark.asyncio
async def test_get_policy_and_missing_version():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "w1"})
            await client.post(
                "/worlds/w1/policies",
                json={"policy": {"top_k": {"metric": "m", "k": 1}}},
            )

            r = await client.get("/worlds/w1/policies/1")
            assert r.status_code == 200
            payload = r.json()
            assert payload["thresholds"] == {}
            assert payload["top_k"] == {"metric": "m", "k": 1}
            assert payload.get("correlation") is None
            assert payload.get("hysteresis") is None
            assert payload.get("validation_profiles", {}) == {}
            assert payload.get("default_profile_by_stage", {}) == {}
            assert payload.get("selection", {}).get("top_k") == {"metric": "m", "k": 1}

            r = await client.get("/worlds/w1/policies/2")
            assert r.status_code == 404
