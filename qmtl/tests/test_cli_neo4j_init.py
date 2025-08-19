import pytest

from qmtl.dagmanager import cli
import qmtl.dagmanager.neo4j_init as neo4j_init


class _FakeSession:
    def __init__(self):
        self.run_calls = []

    def run(self, stmt):
        self.run_calls.append(stmt)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class _FakeDriver:
    def __init__(self):
        self.session_obj = _FakeSession()
        self.closed = False

    def session(self):
        return self.session_obj

    def close(self):
        self.closed = True


def test_neo4j_init_executes_queries(monkeypatch):
    driver = _FakeDriver()

    def fake_connect(uri, user, password):
        return driver

    monkeypatch.setattr(neo4j_init, "connect", fake_connect)
    monkeypatch.setattr(neo4j_init, "get_schema_queries", lambda: ["A", "B"])

    cli.main(["neo4j-init", "--uri", "bolt://x", "--user", "u", "--password", "p"])

    assert driver.session_obj.run_calls == ["A", "B"]
    assert driver.closed


def test_init_schema_executes_queries(monkeypatch):
    driver = _FakeDriver()

    def fake_connect(uri, user, password):
        return driver

    monkeypatch.setattr(neo4j_init, "connect", fake_connect)
    monkeypatch.setattr(neo4j_init, "get_schema_queries", lambda: ["A", "B"])

    neo4j_init.init_schema("bolt://x", "u", "p")

    assert driver.session_obj.run_calls == ["A", "B"]
    assert driver.closed

