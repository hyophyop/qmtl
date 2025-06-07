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
        first_id = dag["nodes"][0]["node_id"]
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
