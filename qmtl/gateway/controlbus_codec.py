from __future__ import annotations

"""CloudEvents encode/decode helpers for ControlBus.

Two encodings are supported:
- JSON (default): message value is a UTF-8 JSON string.
- "Proto" placeholder: header `content_type=application/cloudevents+proto` is
  set and message value is still JSON-encoded for now. This allows a gradual
  migration to real Protobuf without breaking consumers.
"""

import json
from typing import Any, Dict


PROTO_CONTENT_TYPE = "application/cloudevents+proto"


def encode(event: Dict[str, Any], *, use_proto: bool = False) -> tuple[bytes, list[tuple[str, bytes]]]:
    """Encode a CloudEvent-like dictionary to bytes + headers.

    When ``use_proto=True``, the value remains JSON for now but a content-type
    header is attached so consumers can route via the proto pathway.
    """
    payload = json.dumps(event).encode()
    headers: list[tuple[str, bytes]] = []
    if use_proto:
        headers.append(("content_type", PROTO_CONTENT_TYPE.encode()))
    return payload, headers


def decode(value: bytes, headers: Dict[str, str] | None = None) -> Dict[str, Any]:
    """Decode bytes into a CloudEvent-like dictionary.

    JSON and placeholder "proto" are both JSON-encoded for now.
    """
    try:
        return json.loads(value.decode())
    except Exception:
        return {}


__all__ = ["encode", "decode", "PROTO_CONTENT_TYPE"]

