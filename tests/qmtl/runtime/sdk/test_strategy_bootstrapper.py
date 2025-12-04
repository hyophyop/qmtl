from __future__ import annotations

import pytest

from qmtl.foundation.common.compute_key import ComputeContext
from qmtl.services.gateway.models import StrategyAck
from qmtl.runtime.sdk import StreamInput, Strategy
from qmtl.runtime.sdk import strategy_bootstrapper as bootstrapper_module
from qmtl.runtime.sdk.strategy_bootstrapper import StrategyBootstrapper


class SimpleStrategy(Strategy):
    def setup(self) -> None:
        node = StreamInput(interval="60s", period=1)
        self.add_nodes([node])


class NoExecuteStrategy(Strategy):
    def __init__(self) -> None:
        super().__init__()
        self.finished = False

    def setup(self) -> None:
        node = StreamInput(interval="60s", period=1)
        node.execute = False
        self.add_nodes([node])

    def on_finish(self) -> None:
        super().on_finish()
        self.finished = True


class FakeGatewayClient:
    def __init__(self, response: StrategyAck | dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def post_strategy(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeManager:
    def __init__(self) -> None:
        self.offline_flags: list[bool] = []

    async def resolve_tags(self, *, offline: bool) -> None:
        self.offline_flags.append(offline)


class FakeTagService:
    def __init__(self, gateway_url: str | None) -> None:
        self.gateway_url = gateway_url
        self.applied: list[dict[str, object]] = []
        self.manager = FakeManager()
        self.init_calls: list[dict[str, object | None]] = []

    def init(self, strategy: Strategy, world_id: str | None = None, strategy_id: str | None = None):
        self.init_calls.append({"world_id": world_id, "strategy_id": strategy_id})
        setattr(self.manager, "strategy_id", strategy_id)
        return self.manager

    def apply_queue_map(self, strategy: Strategy, queue_map: dict[str, object]) -> None:
        self.applied.append(queue_map)


class DummyPlane:
    def __init__(self) -> None:
        self.configured: tuple[str | None, str] | None = None

    def configure(self, *, dataset_fingerprint: str | None, execution_domain: str) -> None:
        self.configured = (dataset_fingerprint, execution_domain)


@pytest.mark.asyncio
async def test_strategy_bootstrapper_applies_queue_map(monkeypatch):
    strategy = SimpleStrategy()
    strategy.setup()
    ack = StrategyAck(
        strategy_id="strategy-123",
        queue_map={strategy.nodes[0].node_id: "queue"},
    )
    client = FakeGatewayClient(ack)
    plane = DummyPlane()
    created_services: list[FakeTagService] = []

    def make_service(url: str | None) -> FakeTagService:
        svc = FakeTagService(url)
        created_services.append(svc)
        return svc

    monkeypatch.setattr(bootstrapper_module, "TagManagerService", make_service)

    context = ComputeContext(world_id="w1", execution_domain="live")
    result = await StrategyBootstrapper(client).bootstrap(
        strategy,
        context=context,
        world_id="w1",
        gateway_url="http://gateway",
        meta={"dataset_fingerprint": "fp-123"},
        offline=False,
        kafka_available=True,
        trade_mode="live",
        schema_enforcement="strict",
        feature_plane=plane,
    )

    assert not result.completed
    assert result.offline_mode is False
    assert plane.configured == ("fp-123", context.execution_domain)
    assert getattr(strategy.nodes[0], "dataset_fingerprint") == "fp-123"
    assert getattr(strategy.nodes[0], "_schema_enforcement") == "strict"
    assert client.calls  # gateway invoked
    service = created_services[-1]
    assert service.applied == [{strategy.nodes[0].node_id: "queue"}]
    assert service.init_calls[-1]["strategy_id"] == "strategy-123"
    assert getattr(service.manager, "strategy_id") == "strategy-123"
    assert getattr(strategy, "strategy_id") == "strategy-123"
    assert result.strategy_id == "strategy-123"
    assert service.manager.offline_flags == [False]


@pytest.mark.asyncio
async def test_strategy_bootstrapper_ignores_execution_domain_meta(monkeypatch):
    strategy = SimpleStrategy()
    strategy.setup()
    ack = StrategyAck(
        strategy_id="strategy-999",
        queue_map={strategy.nodes[0].node_id: "queue"},
    )
    client = FakeGatewayClient(ack)
    monkeypatch.setattr(bootstrapper_module, "TagManagerService", lambda url: FakeTagService(url))

    context = ComputeContext(world_id="w1", execution_domain="live")
    _ = await StrategyBootstrapper(client).bootstrap(
        strategy,
        context=context,
        world_id="w1",
        gateway_url="http://gateway",
        meta={"execution_domain": "paper", "dataset_fingerprint": "fp-x"},
        offline=False,
        kafka_available=True,
        trade_mode="live",
        schema_enforcement="strict",
        feature_plane=DummyPlane(),
    )

    assert client.calls
    sent_meta = client.calls[-1].get("meta")
    assert isinstance(sent_meta, dict)
    assert "execution_domain" not in sent_meta
    assert sent_meta.get("dataset_fingerprint") == "fp-x"


@pytest.mark.asyncio
async def test_strategy_bootstrapper_handles_no_executable_nodes(monkeypatch):
    strategy = NoExecuteStrategy()
    strategy.setup()
    client = FakeGatewayClient({})
    fake_service = FakeTagService(None)
    monkeypatch.setattr(bootstrapper_module, "TagManagerService", lambda url: fake_service)

    context = ComputeContext(world_id="w2", execution_domain="backtest")
    result = await StrategyBootstrapper(client).bootstrap(
        strategy,
        context=context,
        world_id="w2",
        gateway_url=None,
        meta=None,
        offline=True,
        kafka_available=False,
        trade_mode="simulate",
        schema_enforcement="fail",
        feature_plane=None,
    )

    assert result.completed is True
    assert strategy.finished is True
    assert fake_service.manager.offline_flags == []  # resolve_tags not called when completed
    assert result.strategy_id is None
