from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DagManagerConfig:
    """Configuration for DAG Manager server."""
    neo4j_dsn: Optional[str] = None
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"
    memory_repo_path: str = "memrepo.gpickle"
    kafka_dsn: Optional[str] = None
    kafka_breaker_threshold: int = 3
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    diff_callback: Optional[str] = None
    gc_callback: Optional[str] = None
