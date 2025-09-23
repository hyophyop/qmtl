import base64
import json
import logging

import httpx
import pytest

from qmtl.dagmanager.kafka_admin import compute_key, partition_key
from qmtl.gateway.models import StrategyAck
from qmtl.sdk.execution_context import resolve_execution_context
from qmtl.sdk.runner import Runner
from tests.sample_strategy import SampleStrategy


def test_run_logs(caplog, gateway_mock, runner_with_gateway):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    gateway_mock(handler)

    with caplog.at_level(logging.INFO):
        strategy = runner_with_gateway()

    messages = [record.getMessage() for record in caplog.records]
    assert any("[RUN] SampleStrategy world=w" in msg for msg in messages)
    assert isinstance(strategy, SampleStrategy)


def test_run_queue_map_applied(runner_with_gateway):
    strategy = runner_with_gateway()
    assert isinstance(strategy, SampleStrategy)


def test_run_live_like_path(runner_with_gateway):
    strategy = runner_with_gateway()
    assert isinstance(strategy, SampleStrategy)


def test_gateway_queue_mapping(gateway_mock, runner_with_gateway):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        dag = json.loads(base64.b64decode(payload["dag_json"]).decode())
        first_node = dag["nodes"][0]
        key = partition_key(
            first_node["node_id"],
            first_node.get("interval"),
            0,
            compute_key=compute_key(first_node["node_id"]),
        )
        return httpx.Response(
            202,
            json={"strategy_id": "s1", "queue_map": {key: "topic1"}},
        )

    gateway_mock(handler)
    strategy = runner_with_gateway()
    first_node = strategy.nodes[0]
    assert first_node.kafka_topic == "topic1"
    assert not first_node.execute


def test_run_exits_when_all_nodes_mapped(monkeypatch, caplog):
    async def fake_post_gateway_async(*, gateway_url, dag, meta, context=None, world_id=None):
        queue_map = {node["node_id"]: "topic" for node in dag["nodes"]}
        return StrategyAck(strategy_id="strategy-test", queue_map=queue_map)

    def fake_run_pipeline(strategy):
        raise RuntimeError("should not run")

    monkeypatch.setattr(
        Runner.services().gateway_client,
        "post_strategy",
        fake_post_gateway_async,
    )
    monkeypatch.setattr(Runner, "run_pipeline", fake_run_pipeline)

    with caplog.at_level(logging.INFO):
        strategy = Runner.run(SampleStrategy, world_id="w", gateway_url="http://gw")

    messages = [record.getMessage() for record in caplog.records]
    assert any("No executable nodes" in message for message in messages)
    assert all(not node.execute for node in strategy.nodes)


def test_run_exits_when_all_nodes_mapped_live(monkeypatch, caplog):
    from qmtl.sdk.tagquery_manager import TagQueryManager

    async def fake_post_gateway_async(*, gateway_url, dag, meta, context=None, world_id=None):
        queue_map = {node["node_id"]: "topic" for node in dag["nodes"]}
        return StrategyAck(strategy_id="strategy-test", queue_map=queue_map)

    def fake_run_pipeline(strategy):
        raise RuntimeError("should not run")

    async def fake_start(self):
        raise RuntimeError("should not start")

    monkeypatch.setattr(
        Runner.services().gateway_client,
        "post_strategy",
        fake_post_gateway_async,
    )
    monkeypatch.setattr(Runner, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(TagQueryManager, "start", fake_start)

    with caplog.at_level(logging.INFO):
        strategy = Runner.run(SampleStrategy, world_id="w", gateway_url="http://gw")

    messages = [record.getMessage() for record in caplog.records]
    assert any("No executable nodes" in message for message in messages)
    assert all(not node.execute for node in strategy.nodes)


def test_gateway_error(gateway_mock):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409)

    gateway_mock(handler)

    with pytest.raises(RuntimeError):
        Runner.run(SampleStrategy, world_id="w", gateway_url="http://gw")


def test_connection_failure(monkeypatch):
    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def post(self, url, json=None):
            raise httpx.RequestError("fail", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    with pytest.raises(RuntimeError):
        Runner.run(SampleStrategy, world_id="w", gateway_url="http://gw")


def test_runner_defaults_to_live_when_gateway(monkeypatch):
    Runner.set_default_context(None)
    monkeypatch.setattr(Runner, "_trade_mode", "simulate", raising=False)

    resolution = resolve_execution_context(
        Runner._default_context,
        context=None,
        execution_mode=None,
        execution_domain=None,
        clock=None,
        as_of=None,
        dataset_fingerprint=None,
        offline_requested=False,
        gateway_url="http://gw",
        trade_mode=Runner._trade_mode,
    )

    resolved = resolution.context
    assert resolved["execution_mode"] == "live"
    assert resolved["execution_domain"] == "live"
    assert resolved["clock"] == "wall"
    assert not resolution.force_offline


def test_runner_minimal_path_calls_gateway(runner_with_gateway):
    strategy = runner_with_gateway()
    assert isinstance(strategy, SampleStrategy)


def test_runner_backtest_enforces_virtual_clock(runner_with_gateway):
    Runner.set_default_context(None)
    runner_with_gateway()


def test_runner_live_enforces_wall_clock(runner_with_gateway):
    Runner.set_default_context(None)
    runner_with_gateway()
