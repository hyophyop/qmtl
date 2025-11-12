import asyncio
import types

import pytest

from qmtl.services.dagmanager.config import DagManagerConfig
import qmtl.services.dagmanager.server as server


class _DummyGrpcServer:
    async def start(self) -> None:
        return None

    async def wait_for_termination(self) -> None:
        return None


def _fake_serve(*args, **kwargs):
    return _DummyGrpcServer(), 0


class _StubConfig:
    def __init__(self, app, **kwargs):
        self.app = app
        self.kwargs = kwargs


class _StubHTTPServer:
    def __init__(self, config):
        self.config = config

    async def serve(self) -> None:
        return None


class _ExplodingHTTPServer(_StubHTTPServer):
    async def serve(self) -> None:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_run_starts_and_stops_gc_scheduler(monkeypatch):
    started = asyncio.Event()
    stopped = asyncio.Event()

    class _Scheduler:
        def __init__(self, gc, interval=60.0):
            self.gc = gc

        async def start(self) -> None:
            started.set()

        async def stop(self) -> None:
            stopped.set()

    monkeypatch.setattr(server, "GCScheduler", _Scheduler)
    monkeypatch.setattr(server, "serve", _fake_serve)
    monkeypatch.setattr(
        server,
        "uvicorn",
        types.SimpleNamespace(Config=_StubConfig, Server=_StubHTTPServer),
    )

    cfg = DagManagerConfig()
    cfg.memory_repo_path = None
    await server._run(cfg)

    assert started.is_set()
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_run_stops_scheduler_on_http_failure(monkeypatch):
    stopped = asyncio.Event()

    class _Scheduler:
        def __init__(self, gc, interval=60.0):
            self.gc = gc

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            stopped.set()

    monkeypatch.setattr(server, "GCScheduler", _Scheduler)
    monkeypatch.setattr(server, "serve", _fake_serve)
    monkeypatch.setattr(
        server,
        "uvicorn",
        types.SimpleNamespace(Config=_StubConfig, Server=_ExplodingHTTPServer),
    )

    cfg = DagManagerConfig()
    cfg.memory_repo_path = None
    with pytest.raises(RuntimeError):
        await server._run(cfg)

    assert stopped.is_set()
