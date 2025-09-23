from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Optional

from .connections import ConnectionRegistry


logger = logging.getLogger(__name__)


class ServerManager:
    """Lifecycle wrapper around the optional standalone WebSocket server."""

    def __init__(
        self,
        registry: ConnectionRegistry,
        *,
        on_client_join: Callable[[Any], Awaitable[None]] | None = None,
        on_client_leave: Callable[[Any], Awaitable[None]] | None = None,
    ) -> None:
        self._registry = registry
        self._server: Optional[Any] = None
        self._port: Optional[int] = None
        self._on_client_join = on_client_join
        self._on_client_leave = on_client_leave
        self._lock = asyncio.Lock()

    async def ensure_running(self, *, start_server: bool) -> int:
        async with self._lock:
            if self._server is not None:
                return int(self._port or 0)
            if not self._should_start(start_server):
                return int(self._port or 0)
            try:
                import websockets
            except Exception:  # pragma: no cover - import error already logged elsewhere
                logger.exception("Failed to import websockets server")
                self._port = 0
                return 0

            async def _acceptor(sock):
                await self._registry.add(sock)
                if self._on_client_join is not None:
                    await self._on_client_join(sock)
                try:
                    while True:
                        await sock.recv()
                except Exception:
                    pass
                finally:
                    await self._registry.remove(sock)
                    if self._on_client_leave is not None:
                        await self._on_client_leave(sock)

            try:
                self._server = await websockets.serve(_acceptor, "127.0.0.1", 0)
            except Exception:
                logger.exception("Failed to start internal WebSocket server")
                self._port = 0
                return 0
            sockets = getattr(self._server, "sockets", None) or []
            if sockets:
                self._port = sockets[0].getsockname()[1]
            else:
                self._port = 0
            return int(self._port or 0)

    async def stop(self) -> None:
        async with self._lock:
            server = self._server
            self._server = None
            self._port = None
        if server is None:
            return
        try:
            server.close()
            await server.wait_closed()
        except Exception:
            logger.exception("Failed to stop internal WebSocket server")

    def _should_start(self, start_server: bool) -> bool:
        if start_server:
            return True
        return os.getenv("QMTL_WS_ENABLE_SERVER", "0") == "1"
