from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import yaml


@dataclass
class DagManagerConfig:
    """Configuration for DAG manager server."""
    neo4j_dsn: Optional[str] = None
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"
    memory_repo_path: str = "memrepo.gpickle"
    kafka_dsn: Optional[str] = None
    kafka_breaker_threshold: int = 3
    kafka_breaker_timeout: float = 60.0
    neo4j_breaker_threshold: int = 3
    neo4j_breaker_timeout: float = 60.0
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    diff_callback: Optional[str] = None
    gc_callback: Optional[str] = None


def load_dagmanager_config(path: str) -> DagManagerConfig:
    """Load :class:`DagManagerConfig` from a YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise TypeError("DagManager config must be a mapping")
    return DagManagerConfig(**data)
