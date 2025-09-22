"""Repository interfaces for DAG diff operations."""

from __future__ import annotations

from typing import Dict, Iterable

from qmtl.common import AsyncCircuitBreaker

from .models import NodeRecord

__all__ = ["NodeRepository"]


class NodeRepository:
    """Interface to fetch node metadata and manage buffering state."""

    def get_nodes(
        self,
        node_ids: Iterable[str],
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> Dict[str, NodeRecord]:
        raise NotImplementedError

    def insert_sentinel(
        self,
        sentinel_id: str,
        node_ids: Iterable[str],
        version: str,
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        raise NotImplementedError

    def get_queues_by_tag(
        self,
        tags: Iterable[str],
        interval: int,
        match_mode: str = "any",
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> list[dict[str, object]]:
        raise NotImplementedError

    def get_node_by_queue(
        self,
        queue: str,
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> NodeRecord | None:
        raise NotImplementedError

    # buffering -------------------------------------------------------------

    def mark_buffering(
        self,
        node_id: str,
        *,
        compute_key: str | None = None,
        timestamp_ms: int | None = None,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        raise NotImplementedError

    def clear_buffering(
        self,
        node_id: str,
        *,
        compute_key: str | None = None,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        raise NotImplementedError

    def get_buffering_nodes(
        self,
        older_than_ms: int,
        *,
        compute_key: str | None = None,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> list[str]:
        raise NotImplementedError
