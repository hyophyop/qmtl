import pytest
import sys
import types
import redis.asyncio as redis

from qmtl.common.reconnect import ReconnectingRedis, ReconnectingNeo4j


class DummyRedis:
    def __init__(self, fail_first: bool = True):
        self.calls = 0
        self.fail_first = fail_first

    async def ping(self):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("fail")
        return True


class DummySession:
    def __init__(self, should_fail=True):
        self.should_fail = should_fail
        self.calls = 0

    def run(self, q, **p):
        self.calls += 1
        if self.should_fail and self.calls == 1:
            raise RuntimeError("fail")
        return "ok"

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class DummyDriver:
    def __init__(self, fail=True):
        self.fail = fail
        self.session_created = 0

    def session(self):
        self.session_created += 1
        return DummySession(self.fail and self.session_created == 1)

    def close(self):
        pass


@pytest.mark.asyncio
async def test_reconnecting_redis(monkeypatch):
    r1 = DummyRedis()
    r2 = DummyRedis(fail_first=False)
    calls = [r1, r2]

    def from_url(url, **opts):
        return calls.pop(0)

    monkeypatch.setattr(redis, "from_url", from_url)
    client = ReconnectingRedis("redis://")

    await client.ping()
    assert r1.calls == 1
    assert r2.calls == 1


def test_reconnecting_neo4j(monkeypatch):
    driver1 = DummyDriver(True)
    driver2 = DummyDriver(False)
    drivers = [driver1, driver2]

    class FakeGraphDB:
        @staticmethod
        def driver(uri, auth):
            return drivers.pop(0)

    monkeypatch.setitem(sys.modules, 'neo4j', types.SimpleNamespace(GraphDatabase=FakeGraphDB))

    client = ReconnectingNeo4j('bolt://', 'u', 'p')
    with client.session() as sess:
        assert sess.run('Q') == 'ok'
    assert driver2.session_created >= 1
