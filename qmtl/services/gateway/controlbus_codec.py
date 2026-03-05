from __future__ import annotations

"""JSON encode/decode helpers for the public ControlBus surface."""

import json
from typing import Any, Dict


def encode(event: Dict[str, Any]) -> tuple[bytes, list[tuple[str, bytes]]]:
    """Encode a ControlBus event as UTF-8 JSON bytes plus broker headers."""
    return json.dumps(event).encode(), []


def decode(value: bytes | bytearray | str) -> Dict[str, Any]:
    """Decode UTF-8 JSON payloads into ControlBus event dictionaries."""
    try:
        raw = value.decode() if isinstance(value, (bytes, bytearray)) else value
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


__all__ = ["encode", "decode"]
