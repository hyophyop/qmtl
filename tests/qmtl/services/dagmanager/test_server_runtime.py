from __future__ import annotations

import asyncio
import contextlib

import pytest

from qmtl.services.dagmanager.config import DagManagerConfig
from qmtl.services.dagmanager import server


class _StopEventServer:
    def __init__(self, stop_event: asyncio.Event) -> None:
        self._stop_event = stop_event
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def wait_for_termination(self) -> None:
        await self._stop_event.wait()


class _FailingHttpServer:
    def __init__(self, exc: Exception | None, stop_event: asyncio.Event | None = None) -> None:
        self._exc = exc
        self._stop_event = stop_event

    async def serve(self) -> None:
        if self._exc is not None:
            raise self._exc
        assert self._stop_event is not None
        await self._stop_event.wait()


@pytest.mark.asyncio
async def test_run_starts_and_stops_gc_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    stop_event = asyncio.Event()
    created_schedulers: list[object] = []

    class _Scheduler:
        def __init__(self, gc, *, interval: float) -> None:
            self.gc = gc
            self.interval = interval
            self.started = False
            self.stopped = False
            created_schedulers.append(self)

        async def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

    def fake_serve(*args, **kwargs):
        return _StopEventServer(stop_event), 0

    def fake_uvicorn_server(config):
        return _FailingHttpServer(None, stop_event)

    monkeypatch.setattr(server, "GCScheduler", _Scheduler)
    monkeypatch.setattr(server, "serve", fake_serve)
    monkeypatch.setattr(server.uvicorn, "Server", fake_uvicorn_server)

    cfg = DagManagerConfig(gc_interval_seconds=12.5)

    async def trigger_stop() -> None:
        await asyncio.sleep(0.01)
        stop_event.set()

    stopper = asyncio.create_task(trigger_stop())
    try:
        await server._run(cfg)
    finally:
        stopper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stopper

    assert created_schedulers, "scheduler was not instantiated"
    scheduler = created_schedulers[0]
    assert scheduler.started is True
    assert scheduler.stopped is True
    assert scheduler.interval == pytest.approx(12.5)


@pytest.mark.asyncio
async def test_run_stops_scheduler_when_server_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    created_schedulers: list[object] = []

    class _Scheduler:
        def __init__(self, gc, *, interval: float) -> None:
            self.started = False
            self.stopped = False
            created_schedulers.append(self)

        async def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

    def fake_serve(*args, **kwargs):
        return _StopEventServer(asyncio.Event()), 0

    boom = RuntimeError("http failure")

    def fake_uvicorn_server(config):
        return _FailingHttpServer(boom)

    monkeypatch.setattr(server, "GCScheduler", _Scheduler)
    monkeypatch.setattr(server, "serve", fake_serve)
    monkeypatch.setattr(server.uvicorn, "Server", fake_uvicorn_server)

    cfg = DagManagerConfig()

    with pytest.raises(RuntimeError, match="http failure"):
        await server._run(cfg)

    assert created_schedulers, "scheduler was not instantiated"
    scheduler = created_schedulers[0]
    assert scheduler.started is True
    assert scheduler.stopped is True
