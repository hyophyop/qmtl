"""Compute key helpers shared across SDK and services."""

from __future__ import annotations

from blake3 import blake3

from .compute_context import ComputeContext, DEFAULT_EXECUTION_DOMAIN

__all__ = [
    "ComputeContext",
    "DEFAULT_EXECUTION_DOMAIN",
    "compute_compute_key",
]


def compute_compute_key(node_hash: str, context: ComputeContext) -> str:
    """Return a domain-scoped compute key for ``node_hash`` and ``context``."""

    node_part = str(node_hash or "")
    world, domain, as_of, partition = context.hash_components()
    if not domain:
        domain = "backtest"
    payload = "\x1f".join((node_part, world, domain, as_of, partition)).encode()
    return f"blake3:{blake3(payload).hexdigest()}"
