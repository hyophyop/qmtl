import logging
from types import MethodType

import pytest

from qmtl.sdk.runner import Runner
from qmtl.sdk.tag_manager_service import TagManagerService
from tests.sample_strategy import SampleStrategy


class InstrumentedStrategy(SampleStrategy):
    last_instance: "InstrumentedStrategy | None" = None

    def __init__(self) -> None:
        super().__init__()
        InstrumentedStrategy.last_instance = self
        self.last_error: Exception | None = None

    def on_error(self, error: Exception) -> None:
        self.last_error = error


class DummyManager:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.resolve_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1

    async def resolve_tags(self, **kwargs) -> None:
        self.resolve_calls += 1


class DummyActivationManager:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


@pytest.fixture
def reset_runner_services():
    original = Runner.services()
    yield
    Runner.set_services(original)


@pytest.mark.asyncio
async def test_run_async_cleans_up_on_failure(monkeypatch):
    InstrumentedStrategy.last_instance = None
    manager = DummyManager()
    activation_manager = DummyActivationManager()
    services = Runner.services()
    history_calls = {"count": 0}

    async def fake_warmup(self, strategy, **kwargs):
        return None

    def failing_write(self, strategy):
        history_calls["count"] += 1
        raise RuntimeError("snapshot failure")

    async def fake_post_strategy(*args, **kwargs):
        return {}

    def fake_init(self, strategy, *, world_id=None, strategy_id=None):
        setattr(strategy, "tag_query_manager", manager)
        return manager

    def fake_ensure_activation(self, *, gateway_url, world_id):
        self.set_activation_manager(activation_manager)
        return activation_manager

    monkeypatch.setattr(
        services.history_service.__class__,
        "warmup_strategy",
        fake_warmup,
        raising=False,
    )
    monkeypatch.setattr(
        services.history_service.__class__,
        "write_snapshots",
        failing_write,
        raising=False,
    )
    monkeypatch.setattr(
        services.gateway_client,
        "post_strategy",
        fake_post_strategy,
        raising=False,
    )
    monkeypatch.setattr(
        TagManagerService,
        "init",
        fake_init,
        raising=False,
    )
    monkeypatch.setattr(
        services,
        "ensure_activation_manager",
        MethodType(fake_ensure_activation, services),
        raising=False,
    )
    monkeypatch.setattr(
        type(services.kafka_factory),
        "available",
        property(lambda self: True),
        raising=False,
    )

    caught: RuntimeError | None = None
    try:
        await Runner.run_async(InstrumentedStrategy, world_id="w", gateway_url="http://gw")
    except RuntimeError as exc:  # pragma: no cover - exercised in test
        caught = exc

    assert caught is not None, history_calls["count"]
    assert history_calls["count"] == 1
    assert manager.start_calls == 1
    assert manager.stop_calls == 1
    assert manager.resolve_calls == 1
    assert activation_manager.start_calls == 1
    assert activation_manager.stop_calls == 1
    strategy = InstrumentedStrategy.last_instance
    assert strategy is not None
    assert isinstance(strategy.last_error, RuntimeError)


@pytest.mark.asyncio
async def test_shutdown_async_raises_and_logs(caplog, reset_runner_services):
    class FailingManager:
        def __init__(self) -> None:
            self.stop_calls = 0

        async def stop(self) -> None:
            self.stop_calls += 1
            raise RuntimeError("tag failure")

    class FailingActivation:
        def __init__(self) -> None:
            self.stop_calls = 0

        async def stop(self) -> None:
            self.stop_calls += 1
            raise RuntimeError("activation failure")

    failing_manager = FailingManager()
    failing_activation = FailingActivation()

    strategy = InstrumentedStrategy()
    setattr(strategy, "tag_query_manager", failing_manager)

    services = Runner.services()
    previous_activation = services.activation_manager
    services.set_activation_manager(failing_activation)

    try:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError) as excinfo:
                await Runner.shutdown_async(strategy)
    finally:
        services.set_activation_manager(previous_activation)

    assert "tag failure" in str(excinfo.value)
    assert failing_manager.stop_calls == 1
    assert failing_activation.stop_calls == 1
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "Failed to stop TagQueryManager" in messages
    assert "Failed to stop ActivationManager" in messages
