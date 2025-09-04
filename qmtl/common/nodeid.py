from __future__ import annotations

"""Deterministic NodeID helpers."""

import hashlib
from typing import Iterable


def compute_node_id(
    node_type: str,
    code_hash: str,
    config_hash: str,
    schema_hash: str,
    world_id: str,
    existing_ids: Iterable[str] | None = None,
) -> str:
    """Return deterministic node ID with SHA-256 and SHA-3 fallback.

    Parameters
    ----------
    node_type, code_hash, config_hash, schema_hash : str
        Components defining the node.
    world_id : str
        Identifier of the world this node belongs to.
    existing_ids : Iterable[str] | None
        Previously generated IDs to detect collisions. If the computed SHA-256
        hash already exists in this set, SHA-3-256 is used instead.
    """
    # Include world_id to guarantee isolation across worlds
    data = f"{world_id}:{node_type}:{code_hash}:{config_hash}:{schema_hash}".encode()
    try:
        sha = hashlib.sha256(data).hexdigest()
    except Exception:  # pragma: no cover - unlikely
        return hashlib.sha3_256(data).hexdigest()

    if existing_ids and sha in set(existing_ids):
        sha = hashlib.sha3_256(data).hexdigest()
    return sha


__all__ = ["compute_node_id"]
