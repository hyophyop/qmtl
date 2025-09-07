from __future__ import annotations

"""Deterministic NodeID helpers."""

import hashlib
from typing import Iterable

from blake3 import blake3


def compute_node_id(
    node_type: str,
    code_hash: str,
    config_hash: str,
    schema_hash: str,
    existing_ids: Iterable[str] | None = None,
) -> str:
    """Return canonical BLAKE3-based NodeID with ``blake3:`` prefix.

    Parameters
    ----------
    node_type, code_hash, config_hash, schema_hash : str
        Components defining the node.
    existing_ids : Iterable[str] | None
        Previously generated IDs to detect collisions. If the computed digest
        already exists in this set, a different digest is produced by hashing
        a domain-separated payload.
    """
    data = f"{node_type}:{code_hash}:{config_hash}:{schema_hash}".encode()
    digest = blake3(data).hexdigest()
    node_id = f"blake3:{digest}"
    if existing_ids and node_id in set(existing_ids):
        digest = blake3(data + b"|1").hexdigest()
        node_id = f"blake3:{digest}"
    return node_id


def compute_legacy_node_id(
    node_type: str,
    code_hash: str,
    config_hash: str,
    schema_hash: str,
    world_id: str,
    existing_ids: Iterable[str] | None = None,
) -> str:
    """Return legacy SHA-256/sha3 NodeID that includes ``world_id``.

    This is provided for temporary compatibility while migrating to the
    canonical BLAKE3 NodeID.
    """
    data = f"{world_id}:{node_type}:{code_hash}:{config_hash}:{schema_hash}".encode()
    try:
        sha = hashlib.sha256(data).hexdigest()
    except Exception:  # pragma: no cover - unlikely
        return hashlib.sha3_256(data).hexdigest()

    if existing_ids and sha in set(existing_ids):
        sha = hashlib.sha3_256(data).hexdigest()
    return sha


__all__ = ["compute_node_id", "compute_legacy_node_id"]
