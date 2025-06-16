from __future__ import annotations

"""Connection wrappers with automatic reconnection."""

from typing import Any, Callable

import redis.asyncio as redis


class ReconnectingRedis:
    """Redis client that reconnects on errors."""

    def __init__(self, dsn: str, *, attempts: int = 2, **opts: Any) -> None:
        self._dsn = dsn
        self._opts = {"decode_responses": True}
        self._opts.update(opts)
        self._attempts = attempts
        self._client = redis.from_url(self._dsn, **self._opts)

    async def _reconnect(self) -> None:
        self._client = redis.from_url(self._dsn, **self._opts)

    def __getattr__(self, name: str) -> Callable[..., Any]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            method = getattr(self._client, name)
            try:
                return await method(*args, **kwargs)
            except Exception:
                await self._reconnect()
                method = getattr(self._client, name)
                return await method(*args, **kwargs)

        return wrapper


class _ReconnectingSession:
    def __init__(self, factory: Callable[[], Any], reconnect: Callable[[], None]) -> None:
        self._factory = factory
        self._reconnect = reconnect
        self._session = self._factory()

    def run(self, *args: Any, **kwargs: Any) -> Any:
        for attempt in range(2):
            try:
                return self._session.run(*args, **kwargs)
            except Exception:
                if attempt == 1:
                    raise
                self._session.close()
                self._reconnect()
                self._session = self._factory()
        raise RuntimeError("unreachable")

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "_ReconnectingSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._session.close()


class ReconnectingNeo4j:
    """Neo4j driver wrapper with reconnection logic."""

    def __init__(self, uri: str, user: str, password: str, *, attempts: int = 2) -> None:
        from neo4j import GraphDatabase

        self._uri = uri
        self._auth = (user, password)
        self._attempts = attempts
        self._GraphDatabase = GraphDatabase
        self._driver = GraphDatabase.driver(self._uri, auth=self._auth)

    def _reconnect(self) -> None:
        self._driver.close()
        self._driver = self._GraphDatabase.driver(self._uri, auth=self._auth)

    def session(self, *args: Any, **kwargs: Any) -> _ReconnectingSession:
        def factory():
            return self._driver.session(*args, **kwargs)

        return _ReconnectingSession(factory, self._reconnect)

    def close(self) -> None:
        self._driver.close()


__all__ = ["ReconnectingRedis", "ReconnectingNeo4j"]
