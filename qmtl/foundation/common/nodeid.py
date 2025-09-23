from __future__ import annotations

"""Deterministic NodeID helpers."""

from collections.abc import Iterable, Mapping
from typing import Any

from blake3 import blake3

from .nodespec import CanonicalNodeSpec, serialize_nodespec


def hash_blake3(data: bytes, existing_ids: Iterable[str] | None = None) -> str:
    """Return a ``blake3:``-prefixed digest for ``data``.

    Parameters
    ----------
    data : bytes
        Payload to hash.
    existing_ids : Iterable[str] | None
        Optional set of already issued identifiers used to avoid collisions.
        If provided and the computed digest already exists within ``existing_ids``
        a deterministic suffix is appended to the payload and re-hashed until a
        unique digest is produced.
    """

    digest = blake3(data).hexdigest()
    identifier = f"blake3:{digest}"

    if not existing_ids:
        return identifier

    seen = set(existing_ids)
    if identifier not in seen:
        return identifier

    counter = 1
    while True:
        digest = blake3(data + f"|{counter}".encode()).hexdigest()
        identifier = f"blake3:{digest}"
        if identifier not in seen:
            return identifier
        counter += 1


def compute_node_id(
    node: Mapping[str, Any] | CanonicalNodeSpec,
    *,
    existing_ids: Iterable[str] | None = None,
) -> str:
    """Return canonical BLAKE3-based NodeID with ``blake3:`` prefix.

    The digest is computed from the canonical serialization of the node as
    produced by :func:`qmtl.foundation.common.nodespec.serialize_nodespec`.
    """

    data = serialize_nodespec(node)
    return hash_blake3(data, existing_ids=existing_ids)


__all__ = ["hash_blake3", "compute_node_id"]
