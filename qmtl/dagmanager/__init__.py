import hashlib
from typing import Iterable


def compute_node_id(
    node_type: str,
    code_hash: str,
    config_hash: str,
    schema_hash: str,
    existing_ids: Iterable[str] | None = None,
) -> str:
    """Return deterministic node ID with SHA-256 and SHA-3 fallback.

    Parameters
    ----------
    node_type, code_hash, config_hash, schema_hash : str
        Components defining the node.
    existing_ids : Iterable[str] | None
        Previously generated IDs to detect collisions. If the computed SHA-256
        hash already exists in this set, SHA-3-256 is used instead.
    """
    data = f"{node_type}:{code_hash}:{config_hash}:{schema_hash}".encode()
    try:
        sha = hashlib.sha256(data).hexdigest()
    except Exception:  # pragma: no cover - unlikely
        sha = hashlib.sha3_256(data).hexdigest()
        return sha

    if existing_ids and sha in set(existing_ids):
        sha = hashlib.sha3_256(data).hexdigest()
    return sha


from .topic import TopicConfig, topic_name, get_config
from .kafka_admin import KafkaAdmin
from .gc import GarbageCollector, DEFAULT_POLICY, S3ArchiveClient
from .alerts import PagerDutyClient, SlackClient, AlertManager
from .monitor import Monitor, MonitorLoop

__all__ = [
    "compute_node_id",
    "TopicConfig",
    "topic_name",
    "get_config",
    "KafkaAdmin",
    "GarbageCollector",
    "DEFAULT_POLICY",
    "S3ArchiveClient",
    "PagerDutyClient",
    "SlackClient",
    "AlertManager",
    "Monitor",
    "MonitorLoop",
]
