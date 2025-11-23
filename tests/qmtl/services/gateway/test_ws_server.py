import logging
import sys

import pytest

from qmtl.services.gateway.ws.connections import ConnectionRegistry
from qmtl.services.gateway.ws.server import ServerManager


class FakeServer:
    def __init__(self, handler, port: int = 8765) -> None:
        self.handler = handler
        self.sockets = [self]
        self._addr = ("127.0.0.1", port)
        self.closed = False
        self.waited = False

    def getsockname(self):
        return self._addr

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.waited = True


class FakeWebSockets:
    def __init__(self, *, fail: bool = False, port: int = 8765) -> None:
        self.fail = fail
        self.port = port
        self.server: FakeServer | None = None
        self.served = 0

    async def serve(self, handler, host: str, port: int):
        self.served += 1
        if self.fail:
            raise RuntimeError("bind failed")
        self.server = FakeServer(handler, self.port)
        return self.server


class FakeSocket:
    def __init__(self) -> None:
        self.recv_called = 0

    async def recv(self):
        self.recv_called += 1
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_server_manager_handles_client_lifecycle(monkeypatch):
    registry = ConnectionRegistry()
    joined: list[object] = []
    left: list[object] = []
    ws_mod = FakeWebSockets(port=9876)
    monkeypatch.setitem(sys.modules, "websockets", ws_mod)

    async def on_join(sock):
        joined.append(sock)

    async def on_leave(sock):
        left.append(sock)

    manager = ServerManager(
        registry, on_client_join=on_join, on_client_leave=on_leave
    )

    port = await manager.ensure_running(start_server=True)
    assert port == 9876
    assert ws_mod.server is not None

    sock = FakeSocket()
    await ws_mod.server.handler(sock)

    assert joined == [sock]
    assert left == [sock]
    assert await registry.all_clients() == []

    await manager.stop()
    assert ws_mod.server.closed is True
    assert ws_mod.server.waited is True


@pytest.mark.asyncio
async def test_server_manager_logs_start_failure(monkeypatch, caplog):
    registry = ConnectionRegistry()
    ws_mod = FakeWebSockets(fail=True)
    monkeypatch.setitem(sys.modules, "websockets", ws_mod)
    monkeypatch.setenv("QMTL_WS_ENABLE_SERVER", "1")
    manager = ServerManager(registry)

    with caplog.at_level(logging.ERROR):
        port = await manager.ensure_running(start_server=False)

    assert port == 0
    assert manager._server is None  # type: ignore[attr-defined]
    assert any("Failed to start internal WebSocket server" in r.message for r in caplog.records)
