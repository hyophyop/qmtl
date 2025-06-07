import sys
import base64
import json

import httpx
import pytest
from qmtl.sdk.runner import Runner
from tests.sample_strategy import SampleStrategy


def test_backtest(capsys):
    strategy = Runner.backtest(SampleStrategy, start_time="s", end_time="e")
    captured = capsys.readouterr().out
    assert "[BACKTEST] SampleStrategy" in captured
    assert isinstance(strategy, SampleStrategy)


def test_dryrun(capsys):
    strategy = Runner.dryrun(SampleStrategy)
    captured = capsys.readouterr().out
    assert "[DRYRUN] SampleStrategy" in captured
    assert isinstance(strategy, SampleStrategy)


def test_live(capsys):
    strategy = Runner.live(SampleStrategy)
    captured = capsys.readouterr().out
    assert "[LIVE] SampleStrategy" in captured
    assert isinstance(strategy, SampleStrategy)


def test_gateway_queue_mapping(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        dag = json.loads(base64.b64decode(payload["dag_json"]).decode())
        first_node = dag["nodes"][0]
        assert "code_hash" in first_node and "schema_hash" in first_node
        first_id = first_node["node_id"]
        return httpx.Response(
            202,
            json={"strategy_id": "s1", "queue_map": {first_id: "topic1"}},
        )

    transport = httpx.MockTransport(handler)

    def mock_post(url, json):
        with httpx.Client(transport=transport) as client:
            return client.post(url, json=json)

    monkeypatch.setattr(httpx, "post", mock_post)

    strategy = Runner.dryrun(SampleStrategy, gateway_url="http://gw")
    first_node = strategy.nodes[0]
    assert first_node.queue_topic == "topic1"
    assert not first_node.execute


def test_gateway_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409)

    transport = httpx.MockTransport(handler)

    def mock_post(url, json):
        with httpx.Client(transport=transport) as client:
            return client.post(url, json=json)

    monkeypatch.setattr(httpx, "post", mock_post)

    with pytest.raises(RuntimeError):
        Runner.dryrun(SampleStrategy, gateway_url="http://gw")


def test_offline_flag():
    strategy = Runner.dryrun(SampleStrategy, gateway_url="http://gw", offline=True)
    assert all(n.execute for n in strategy.nodes)
    assert all(n.queue_topic is None for n in strategy.nodes)


def test_connection_failure(monkeypatch):
    def mock_post(url, json):
        raise httpx.RequestError("fail", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", mock_post)

    strategy = Runner.dryrun(SampleStrategy, gateway_url="http://gw")
    assert all(n.execute for n in strategy.nodes)
    assert all(n.queue_topic is None for n in strategy.nodes)
    offline = Runner.dryrun(SampleStrategy, offline=True)
    assert [n.node_id for n in offline.nodes] == [n.node_id for n in strategy.nodes]


def test_offline_same_ids(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    transport = httpx.MockTransport(handler)

    def mock_post(url, json):
        with httpx.Client(transport=transport) as client:
            return client.post(url, json=json)

    monkeypatch.setattr(httpx, "post", mock_post)

    online = Runner.dryrun(SampleStrategy, gateway_url="http://gw")
    offline = Runner.dryrun(SampleStrategy, offline=True)
    assert [n.node_id for n in online.nodes] == [n.node_id for n in offline.nodes]


def test_no_gateway_same_ids(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    transport = httpx.MockTransport(handler)

    def mock_post(url, json):
        with httpx.Client(transport=transport) as client:
            return client.post(url, json=json)

    monkeypatch.setattr(httpx, "post", mock_post)

    online = Runner.dryrun(SampleStrategy, gateway_url="http://gw")
    no_gateway = Runner.dryrun(SampleStrategy)
    assert [n.node_id for n in online.nodes] == [n.node_id for n in no_gateway.nodes]
