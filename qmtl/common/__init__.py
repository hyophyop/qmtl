import zlib
from typing import Iterable


def crc32_of_list(items: Iterable[str]) -> int:
    """Return CRC32 for an iterable of strings in order."""
    crc = 0
    for item in items:
        crc = zlib.crc32(item.encode(), crc)
    return crc & 0xFFFFFFFF


from .reconnect import ReconnectingRedis, ReconnectingNeo4j
from .circuit_breaker import AsyncCircuitBreaker
from .four_dim_cache import FourDimCache
from .nodeid import compute_node_id, compute_legacy_node_id

__all__ = [
    "crc32_of_list",
    "ReconnectingRedis",
    "ReconnectingNeo4j",
    "AsyncCircuitBreaker",
    "FourDimCache",
    "compute_node_id",
    "compute_legacy_node_id",
]
