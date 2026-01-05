"""Shared data models for the DAG diff service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


__all__ = [
    "DiffRequest",
    "DiffChunk",
    "NodeInfo",
    "NodeRecord",
    "BufferInstruction",
]


@dataclass
class DiffRequest:
    strategy_id: str
    dag_json: str
    world_id: str | None = None
    execution_domain: str | None = None
    as_of: str | None = None
    partition: str | None = None
    dataset_fingerprint: str | None = None


@dataclass
class NodeInfo:
    node_id: str
    node_type: str
    code_hash: str
    schema_hash: str
    schema_compat_id: str
    interval: int | None
    period: int | None
    tags: list[str]
    bucket: int | None = None
    is_global: bool = False
    compute_key: str | None = field(default=None, init=False)
    compute_keys: tuple[str, ...] = field(default_factory=tuple, kw_only=True)


@dataclass
class NodeRecord(NodeInfo):
    topic: str = ""


@dataclass
class BufferInstruction(NodeInfo):
    lag: int = 0


@dataclass
class DiffChunk:
    queue_map: Dict[str, str]
    sentinel_id: str
    version: str
    crc32: int
    buffering_nodes: List[BufferInstruction] = field(default_factory=list)
    new_nodes: List[NodeInfo] = field(default_factory=list)
