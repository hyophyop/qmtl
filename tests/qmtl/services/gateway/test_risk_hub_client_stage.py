from types import SimpleNamespace

from qmtl.foundation.config import RiskHubConfig
from qmtl.services.gateway.api import _build_risk_hub_client


def test_build_risk_hub_client_inherits_stage_from_config():
    cfg = RiskHubConfig(stage="paper")
    world_client = SimpleNamespace(base_url="http://ws", http_client=None)

    client = _build_risk_hub_client(world_client, cfg, blob_store=None)

    assert client.stage == "paper"
