import pytest

from qmtl.foundation.config import DeploymentProfile
from qmtl.services.gateway.api import create_app
from qmtl.services.gateway.config import GatewayOwnershipConfig
from qmtl.services.gateway.database import PostgresDatabase
from qmtl.services.gateway.ownership import OwnershipManager


@pytest.mark.asyncio
async def test_create_app_wires_kafka_ownership(monkeypatch, fake_redis):
    ownership_cfg = GatewayOwnershipConfig(
        mode="kafka",
        bootstrap="kafka:9092",
        topic="gateway.ownership",
        group_id="locks",
        start_timeout=1.5,
        rebalance_backoff=0.2,
        rebalance_attempts=4,
    )
    captured: dict[str, object] = {}

    fake_owner = object()

    def fake_create_kafka_ownership(bootstrap_servers, topic, group_id, **kwargs):
        captured["args"] = (bootstrap_servers, topic, group_id)
        captured["kwargs"] = kwargs
        return fake_owner

    from qmtl.services.gateway import ownership as ownership_module

    monkeypatch.setattr(
        ownership_module, "create_kafka_ownership", fake_create_kafka_ownership
    )

    db = PostgresDatabase("postgresql://localhost/test")

    app = create_app(
        redis_client=fake_redis,
        database=db,
        ownership_config=ownership_cfg,
        profile=DeploymentProfile.PROD,
    )

    assert app.state.kafka_owner is fake_owner
    assert isinstance(app.state.ownership_manager, OwnershipManager)
    assert captured["args"] == (
        "kafka:9092",
        "gateway.ownership",
        "locks",
    )
    assert captured["kwargs"] == {
        "start_timeout": 1.5,
        "rebalance_backoff": 0.2,
        "rebalance_attempts": 4,
    }
