from __future__ import annotations

"""Common hashing utilities with graceful fallbacks."""

from typing import Final
import hashlib

try:  # pragma: no cover - import guard exercised in fallback tests
    from blake3 import blake3 as _blake3
except Exception:  # pragma: no cover - runtime environments may lack blake3
    _blake3 = None

_BLAKE3_PREFIX: Final[str] = "blake3:"
_SHA256_PREFIX: Final[str] = "sha256:"


def hash_bytes(data: bytes) -> str:
    """Return a deterministic digest string for the given *data* bytes.

    The function prefers BLAKE3 when available and functional, returning the
    digest prefixed with ``"blake3:"``. If the BLAKE3 module is unavailable or
    raises an exception during hashing, it falls back to SHA-256, returning the
    digest prefixed with ``"sha256:"``.
    """

    payload = data if isinstance(data, bytes) else bytes(data)
    if _blake3 is not None:
        try:
            return f"{_BLAKE3_PREFIX}{_blake3(payload).hexdigest()}"
        except Exception:
            pass
    return f"{_SHA256_PREFIX}{hashlib.sha256(payload).hexdigest()}"


__all__ = ["hash_bytes"]
