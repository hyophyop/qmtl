from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import logging
import yaml


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
    http_port: int = 8001
    controlbus_dsn: Optional[str] = None
    controlbus_queue_topic: str = "queue"
    enable_topic_namespace: bool = True
    kafka_metrics_url: Optional[str] = None
    gc_interval_seconds: float = 60.0


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
    # Transitional aliases: allow *_url/*_uri and map to *_dsn if canonical absent
    aliases = {
        "neo4j_url": "neo4j_dsn",
        "neo4j_uri": "neo4j_dsn",
        "kafka_url": "kafka_dsn",
        "kafka_uri": "kafka_dsn",
        "controlbus_url": "controlbus_dsn",
        "controlbus_uri": "controlbus_dsn",
    }
    for alias, canonical in aliases.items():
        if canonical in data:
            data.pop(alias, None)
        elif alias in data:
            data[canonical] = data.pop(alias)
    return DagManagerConfig(**data)
