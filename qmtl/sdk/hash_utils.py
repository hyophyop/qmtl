from __future__ import annotations

"""Reusable hashing helpers for nodes."""

import hashlib
import inspect
import json
from typing import Any


def _sha256(data: bytes) -> str:
    try:
        h = hashlib.sha256()
        h.update(data)
        return h.hexdigest()
    except Exception:
        h = hashlib.sha3_256()
        h.update(data)
        return h.hexdigest()


def _sha3(data: bytes) -> str:
    h = hashlib.sha3_256()
    h.update(data)
    return h.hexdigest()


def code_hash(compute_fn: Any) -> str:
    """Return a stable hash for ``compute_fn``."""
    if compute_fn is None:
        return _sha256(b"null")
    try:
        source = inspect.getsource(compute_fn).encode()
    except (OSError, TypeError):
        source = getattr(compute_fn, "__code__", None)
        if source is not None:
            source = source.co_code
        else:
            source = repr(compute_fn).encode()
    return _sha256(source)


def config_hash(config: dict) -> str:
    data = json.dumps(config, sort_keys=True).encode()
    return _sha256(data)


def schema_hash(schema: dict) -> str:
    data = json.dumps(schema, sort_keys=True).encode()
    return _sha256(data)

__all__ = [
    "_sha256",
    "_sha3",
    "code_hash",
    "config_hash",
    "schema_hash",
]
