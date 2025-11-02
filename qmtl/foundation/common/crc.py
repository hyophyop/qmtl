"""CRC helpers for deterministic validation routines."""

from __future__ import annotations

import zlib
from typing import Iterable


def crc32_of_list(items: Iterable[str]) -> int:
    """Return CRC32 for an iterable of strings in order."""

    crc = 0
    for item in items:
        crc = zlib.crc32(item.encode(), crc)
    return crc & 0xFFFFFFFF


__all__ = ["crc32_of_list"]
