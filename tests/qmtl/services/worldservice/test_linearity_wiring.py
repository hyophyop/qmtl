import httpx
import pytest

from qmtl.services.worldservice.api import create_app
from qmtl.services.worldservice.storage import Storage


@pytest.mark.asyncio
async def test_worldservice_augments_metrics_v2_threshold():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "w1", "name": "World"})
            # Policy with threshold on v2 score
            policy = {
                "thresholds": {
                    "elv2": {"metric": "el_v2_score", "min": 0.7}
                }
            }
            payload = {
                "policy": policy,
                "metrics": {},
                "series": {
                    # linear up — should pass
                    "s_lin": {"equity": [0, 1, 2, 3, 4, 5]},
                    # flat then jump — should fail
                    "s_flat": {"equity": [0.0] * 50 + [1.0]},
                },
            }
            r = await client.post("/worlds/w1/evaluate", json=payload)
            body = r.json()
            assert "s_lin" in body["active"]
            assert "s_flat" not in body["active"]

