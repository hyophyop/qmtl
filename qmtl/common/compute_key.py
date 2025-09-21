"""Compute key helpers shared across SDK and services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from blake3 import blake3

__all__ = [
    "ComputeContext",
    "DEFAULT_EXECUTION_DOMAIN",
    "compute_compute_key",
]


DEFAULT_EXECUTION_DOMAIN = "default"


@dataclass(frozen=True)
class ComputeContext:
    """Describe the execution context for a node compute run."""

    world_id: str = ""
    execution_domain: str = DEFAULT_EXECUTION_DOMAIN
    as_of: Any | None = None
    partition: Any | None = None

    def _canon(self) -> tuple[str, str, str, str]:
        """Return canonical string parts for hashing."""

        world = str(self.world_id or "")
        domain = str(self.execution_domain or "")
        as_of = "" if self.as_of is None else str(self.as_of)
        partition = "" if self.partition is None else str(self.partition)
        return world, domain, as_of, partition


def compute_compute_key(node_hash: str, context: ComputeContext) -> str:
    """Return a domain-scoped compute key for ``node_hash`` and ``context``."""

    node_part = str(node_hash or "")
    payload = "\x1f".join((node_part, *context._canon())).encode()
    return f"blake3:{blake3(payload).hexdigest()}"

