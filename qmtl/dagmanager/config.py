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
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    diff_callback: Optional[str] = None
    gc_callback: Optional[str] = None


def load_dagmanager_config(path: str) -> DagManagerConfig:
    """Load :class:`DagManagerConfig` from a YAML file."""
    logger = logging.getLogger(__name__)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            try:
                data = yaml.safe_load(fh) or {}
            except yaml.YAMLError as exc:
                logger.error("Failed to parse configuration file %s: %s", path, exc)
                raise ValueError(f"Failed to parse configuration file {path}") from exc
    except (FileNotFoundError, OSError) as exc:
        logger.error("Unable to open configuration file %s: %s", path, exc)
        raise
    if not isinstance(data, dict):
        raise TypeError("DAG Manager config must be a mapping")
    # Breaker settings are deprecated; reset breakers manually on success.
    data.pop("kafka_breaker_timeout", None)
    data.pop("kafka_breaker_threshold", None)
    return DagManagerConfig(**data)
