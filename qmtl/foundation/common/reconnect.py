from __future__ import annotations

"""Connection wrappers with automatic reconnection."""

from typing import Any, Callable, Protocol, runtime_checkable

from .circuit_breaker import AsyncCircuitBreaker
import asyncio

import redis.asyncio as redis


@runtime_checkable
class Neo4jSessionLike(Protocol):
    def run(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def close(self) -> None:
        ...

    def __enter__(self) -> "Neo4jSessionLike":
        ...

    def __exit__(self, exc_type, exc, tb) -> None:
        ...


@runtime_checkable
class Neo4jDriverLike(Protocol):
    def session(self, *args: Any, **kwargs: Any) -> Neo4jSessionLike:
        ...

    def close(self) -> None:
        ...


def create_neo4j_driver(uri: str, auth: tuple[str, str]) -> Neo4jDriverLike:
    """Factory that creates a Neo4j driver instance."""

    from neo4j import GraphDatabase

    return GraphDatabase.driver(uri, auth=auth)


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
    def __init__(
        self,
        session_factory: Callable[[], Neo4jSessionLike],
        reconnect: Callable[[], None],
        *,
        attempts: int = 2,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._reconnect = reconnect
        self._attempts = attempts
        self._session: Neo4jSessionLike = self._session_factory()
        self._breaker: AsyncCircuitBreaker | None = breaker

    def _refresh_session(self) -> None:
        self._session.close()
        self._reconnect()
        self._session = self._session_factory()

    def _run_with_breaker(self, *args: Any, **kwargs: Any) -> Any:
        breaker = self._breaker
        assert breaker is not None

        async def _call() -> Any:
            return await asyncio.to_thread(self._session.run, *args, **kwargs)

        async def _execute() -> Any:
            breaker_call = breaker(_call)
            return await breaker_call()

        return asyncio.run(_execute())

    def run(self, *args: Any, **kwargs: Any) -> Any:
        for attempt in range(self._attempts):
            try:
                if self._breaker is None:
                    return self._session.run(*args, **kwargs)
                return self._run_with_breaker(*args, **kwargs)
            except Exception:
                if attempt >= self._attempts - 1:
                    raise
                self._refresh_session()
        raise RuntimeError("unreachable")

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "_ReconnectingSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._session.close()


class ReconnectingNeo4j:
    """Neo4j driver wrapper with reconnection logic."""

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        *,
        attempts: int = 2,
        driver_factory: Callable[[str, tuple[str, str]], Neo4jDriverLike] | None = None,
    ) -> None:
        self._uri = uri
        self._auth = (user, password)
        self._attempts = attempts
        self._driver_factory = driver_factory or create_neo4j_driver
        self._driver: Neo4jDriverLike = self._driver_factory(self._uri, self._auth)

    def _reconnect(self) -> None:
        self._driver.close()
        self._driver = self._driver_factory(self._uri, self._auth)

    def session(
        self,
        *args: Any,
        breaker: AsyncCircuitBreaker | None = None,
        **kwargs: Any,
    ) -> _ReconnectingSession:
        def factory() -> Neo4jSessionLike:
            return self._driver.session(*args, **kwargs)

        return _ReconnectingSession(
            factory,
            self._reconnect,
            attempts=self._attempts,
            breaker=breaker,
        )

    def close(self) -> None:
        self._driver.close()


__all__ = [
    "Neo4jDriverLike",
    "Neo4jSessionLike",
    "create_neo4j_driver",
    "ReconnectingRedis",
    "ReconnectingNeo4j",
]
