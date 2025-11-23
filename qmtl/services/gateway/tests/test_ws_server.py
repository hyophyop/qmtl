import sys
from types import SimpleNamespace

import pytest

from qmtl.services.gateway.ws.connections import ConnectionRegistry
from qmtl.services.gateway.ws.server import ServerManager


class _FakeSocket:
    def __init__(self, port: int) -> None:
        self._port = port

    def getsockname(self):
        return ("127.0.0.1", self._port)


class _FakeServer:
    def __init__(self, port: int) -> None:
        self.sockets = [_FakeSocket(port)]
        self.closed = False
        self.waited = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.waited = True


@pytest.mark.asyncio
async def test_server_manager_starts_and_tracks_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ConnectionRegistry()
    joins: list[object] = []
    leaves: list[object] = []
    captured: dict[str, object] = {}

    async def on_join(sock: object) -> None:
        joins.append(sock)

    async def on_leave(sock: object) -> None:
        leaves.append(sock)

    async def fake_serve(handler, host, port):
        captured["acceptor"] = handler
        return _FakeServer(8765)

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(serve=fake_serve))

    manager = ServerManager(registry, on_client_join=on_join, on_client_leave=on_leave)

    port = await manager.ensure_running(start_server=True)
    assert port == 8765

    acceptor = captured["acceptor"]

    class _Client:
        def __init__(self) -> None:
            self.recv_calls = 0

        async def recv(self) -> None:
            self.recv_calls += 1
            raise RuntimeError("disconnect")

    client = _Client()
    await acceptor(client)  # type: ignore[arg-type]

    assert joins == [client]
    assert leaves == [client]
    assert await registry.all_clients() == []

    await manager.stop()


@pytest.mark.asyncio
async def test_server_manager_respects_start_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ConnectionRegistry()
    starts: list[tuple[str, int]] = []

    async def fake_serve(handler, host, port):
        starts.append((host, port))
        return _FakeServer(0)

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(serve=fake_serve))

    manager = ServerManager(registry)

    port = await manager.ensure_running(start_server=False)
    assert port == 0
    assert starts == []

    monkeypatch.setenv("QMTL_WS_ENABLE_SERVER", "1")
    port = await manager.ensure_running(start_server=False)
    assert port == 0
    assert starts == [("127.0.0.1", 0)]

    port_again = await manager.ensure_running(start_server=False)
    assert port_again == 0
    assert starts == [("127.0.0.1", 0)]

    monkeypatch.delenv("QMTL_WS_ENABLE_SERVER", raising=False)
    await manager.stop()
