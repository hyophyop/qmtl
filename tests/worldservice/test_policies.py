import httpx
import pytest

from qmtl.worldservice.api import create_app


@pytest.mark.asyncio
async def test_get_policy_and_missing_version():
    app = create_app()
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "w1"})
            await client.post(
                "/worlds/w1/policies",
                json={"policy": {"top_k": {"metric": "m", "k": 1}}},
            )

            r = await client.get("/worlds/w1/policies/1")
            assert r.status_code == 200
            assert r.json() == {
                "thresholds": {},
                "top_k": {"metric": "m", "k": 1},
                "correlation": None,
                "hysteresis": None,
            }

            r = await client.get("/worlds/w1/policies/2")
            assert r.status_code == 404

