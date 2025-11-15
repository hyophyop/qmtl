from __future__ import annotations

"""Async wrapper for invoking DAG Manager diff operations."""

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Protocol


@dataclass(slots=True)
class DiffOutcome:
    """Normalized diff response containing sentinel and queue bindings."""

    sentinel_id: str | None
    queue_map: dict[str, list[dict[str, Any]]] | None


def ensure_crc(chunk, expected_crc32: int | None) -> None:
    """Validate that a diff chunk satisfies the negotiated CRC handshake."""

    if expected_crc32 is None or chunk is None:
        return
    has_field = getattr(chunk, "HasField", None)
    if callable(has_field) and not chunk.HasField("crc32"):
        raise ValueError("diff chunk missing CRC32 handshake")
    crc = getattr(chunk, "crc32", None)
    if crc is None:
        raise ValueError("diff chunk missing CRC32 handshake")
    if int(crc) != expected_crc32:
        raise ValueError("diff chunk CRC32 mismatch")


class DiffRunStrategy(Protocol):
    """Strategy protocol for running DAG diff operations."""

    async def execute(self) -> DiffOutcome:
        """Execute the diff run and normalize the outcome."""


InvokeDiff = Callable[[str | None], Awaitable[Any]]


class QueueMapAggregationStrategy:
    """Aggregate queue map bindings across multiple worlds."""

    def __init__(
        self,
        *,
        worlds: Iterable[str],
        invoke: InvokeDiff,
        expected_crc32: int | None,
        node_id_resolver: Callable[[str], str],
    ) -> None:
        self._worlds = list(worlds)
        self._invoke = invoke
        self._expected_crc32 = expected_crc32
        self._node_id_resolver = node_id_resolver

    async def execute(self) -> DiffOutcome:
        tasks = [self._invoke(world_id) for world_id in self._worlds]
        chunks = await asyncio.gather(*tasks, return_exceptions=True)

        sentinel_id: str | None = None
        queue_map: dict[str, list[dict[str, Any]]] = {}

        for chunk in chunks:
            if isinstance(chunk, Exception) or chunk is None:
                continue
            ensure_crc(chunk, self._expected_crc32)
            if not sentinel_id:
                sentinel_id = getattr(chunk, "sentinel_id", None)
            for key, topic in dict(getattr(chunk, "queue_map", {})).items():
                node_id = self._node_id_resolver(str(key))
                entries = queue_map.setdefault(node_id, [])
                if topic not in [d.get("queue") for d in entries]:
                    entries.append({"queue": topic, "global": False})

        return DiffOutcome(sentinel_id=sentinel_id, queue_map=queue_map)


class SingleWorldStrategy:
    """Execute a diff for a single world and normalize the outcome."""

    def __init__(
        self,
        *,
        worlds: list[str],
        fallback_world_id: str | None,
        invoke: InvokeDiff,
        expected_crc32: int | None,
        timeout: float,
        prefer_queue_map: bool,
        node_id_resolver: Callable[[str], str],
    ) -> None:
        self._worlds = worlds
        self._fallback_world_id = fallback_world_id
        self._invoke = invoke
        self._expected_crc32 = expected_crc32
        self._timeout = timeout
        self._prefer_queue_map = prefer_queue_map
        self._node_id_resolver = node_id_resolver

    async def execute(self) -> DiffOutcome:
        sentinel_id: str | None = None
        queue_map: dict[str, list[dict[str, Any]]] | None = None

        world = self._worlds[0] if self._worlds else self._fallback_world_id
        if world is None and self._prefer_queue_map and not self._worlds:
            queue_map = {}

        chunk = await asyncio.wait_for(
            self._invoke(world), timeout=self._timeout
        )
        if chunk is None:
            return DiffOutcome(sentinel_id=sentinel_id, queue_map=queue_map)

        ensure_crc(chunk, self._expected_crc32)

        sentinel_id = getattr(chunk, "sentinel_id", None)
        if self._prefer_queue_map:
            queue_map = {}
            for key, topic in dict(getattr(chunk, "queue_map", {})).items():
                node_id = self._node_id_resolver(str(key))
                queue_map.setdefault(node_id, []).append(
                    {"queue": topic, "global": False}
                )

        return DiffOutcome(sentinel_id=sentinel_id, queue_map=queue_map)


class DiffExecutor:
    """Run DAG Manager diffs and normalize sentinel/queue_map results."""

    def __init__(self, dagmanager) -> None:
        self._dagmanager = dagmanager

    async def run(
        self,
        *,
        strategy_id: str,
        dag_json: str,
        worlds: list[str],
        fallback_world_id: str | None,
        compute_ctx,
        timeout: float,
        prefer_queue_map: bool,
        expected_crc32: int | None = None,
    ) -> DiffOutcome:
        diff_kwargs = compute_ctx.diff_kwargs()

        async def _invoke(world: str | None):
            return await self._dagmanager.diff(
                strategy_id,
                dag_json,
                world_id=world,
                **diff_kwargs,
            )

        if prefer_queue_map and len(worlds) > 1:
            strategy: DiffRunStrategy = QueueMapAggregationStrategy(
                worlds=worlds,
                invoke=_invoke,
                expected_crc32=expected_crc32,
                node_id_resolver=self._node_id_from_partition_key,
            )
        else:
            strategy = SingleWorldStrategy(
                worlds=worlds,
                fallback_world_id=fallback_world_id,
                invoke=_invoke,
                expected_crc32=expected_crc32,
                timeout=timeout,
                prefer_queue_map=prefer_queue_map,
                node_id_resolver=self._node_id_from_partition_key,
            )

        return await strategy.execute()

    def _node_id_from_partition_key(self, identifier: str) -> str:
        base, _, _ = identifier.partition("#")
        token = base or identifier
        if ":" in token:
            return token.rsplit(":", 2)[0]
        return token
