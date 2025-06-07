import httpx
from qmtl.dagmanager.alerts import PagerDutyClient, SlackClient


def test_alert_clients(monkeypatch):
    calls = []

    def fake_post(url, json):
        calls.append((url, json))
        return httpx.Response(202)

    monkeypatch.setattr(httpx, "post", fake_post)

    pd = PagerDutyClient("http://pd")
    sl = SlackClient("http://slack")

    pd.send("neo4j down")
    sl.send("kafka lost")

    assert calls == [
        ("http://pd", {"text": "neo4j down"}),
        ("http://slack", {"text": "kafka lost"}),
    ]
