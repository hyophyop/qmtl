import sys
import types
import pytest

from qmtl.common import AsyncCircuitBreaker
from qmtl.common.reconnect import ReconnectingNeo4j
from qmtl.dagmanager.diff_service import Neo4jNodeRepository


class DummySession:
    def __init__(self, fail=True):
        self.fail = fail
        self.calls = 0

    def run(self, query, **params):
        self.calls += 1
        if self.fail:
            raise RuntimeError("fail")
        return []

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
        self.sessions = []

    def session(self):
        self.session_created += 1
        sess = DummySession(self.fail)
        self.sessions.append(sess)
        return sess

    def close(self):
        pass


def _patch_driver(monkeypatch, drivers):
    class FakeGraphDB:
        @staticmethod
        def driver(uri, auth):
            return drivers.pop(0)

    monkeypatch.setitem(sys.modules, 'neo4j', types.SimpleNamespace(GraphDatabase=FakeGraphDB))


def test_breaker_opens(monkeypatch):
    driver1 = DummyDriver(True)
    driver2 = DummyDriver(True)
    drivers = [driver1, driver2]
    _patch_driver(monkeypatch, drivers)

    client = ReconnectingNeo4j('bolt://', 'u', 'p')
    repo = Neo4jNodeRepository(client)
    breaker = AsyncCircuitBreaker(max_failures=1)

    with pytest.raises(RuntimeError):
        repo.get_nodes(['A'], breaker=breaker)

    assert breaker.is_open
    assert driver1.sessions[0].calls == 1
    assert driver2.sessions[0].calls == 0


def test_breaker_resets(monkeypatch):
    driver1 = DummyDriver(True)
    driver2 = DummyDriver(False)
    drivers = [driver1, driver2]
    _patch_driver(monkeypatch, drivers)

    client = ReconnectingNeo4j('bolt://', 'u', 'p')
    repo = Neo4jNodeRepository(client)
    breaker = AsyncCircuitBreaker(max_failures=1)

    with pytest.raises(RuntimeError):
        repo.get_nodes(['A'], breaker=breaker)

    assert breaker.is_open
    breaker.reset()

    records = repo.get_nodes(['A'], breaker=breaker)
    assert records == {}
    assert not breaker.is_open
    assert driver2.sessions[-1].calls == 1

