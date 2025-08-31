"""Utility helpers for event stream JWT descriptors.

This module provides minimal JWT creation and validation using symmetric
HMAC keys. Keys are identified by ``kid`` allowing rotation. A helper is
also provided to expose the configured keys as a JWKS document so that
external services can validate tokens without sharing secrets.

The implementation intentionally avoids external dependencies to keep the
Gateway lightweight.
"""

from __future__ import annotations

import json
import time
import base64
import hmac
import hashlib
from dataclasses import dataclass
from typing import Any


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


@dataclass
class EventDescriptorConfig:
    """Configuration for signing event stream tokens.

    ``keys`` maps ``kid`` values to HMAC secrets. ``active_kid`` denotes the key
    used for new tokens. Keeping previous keys in the map allows validating
    tokens issued before a rotation.
    """

    keys: dict[str, str]
    active_kid: str
    ttl: int = 300
    stream_url: str = "wss://gateway/ws/evt"
    fallback_url: str = "wss://gateway/ws"


def sign_event_token(claims: dict[str, Any], cfg: EventDescriptorConfig) -> str:
    """Return a signed JWT containing ``claims``."""

    secret = cfg.keys[cfg.active_kid]
    header = {"alg": "HS256", "typ": "JWT", "kid": cfg.active_kid}
    header_b64 = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode()
    )
    payload_b64 = _b64url_encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    )
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def validate_event_token(
    token: str, cfg: EventDescriptorConfig, audience: str = "controlbus"
) -> dict[str, Any]:
    """Validate ``token`` and return its claims.

    Raises ``ValueError`` if the token is invalid, expired or has the wrong
    audience.
    """

    header_b64, payload_b64, sig_b64 = token.split(".")
    header = json.loads(_b64url_decode(header_b64))
    kid = header.get("kid")
    secret = cfg.keys.get(kid)
    if secret is None:
        raise ValueError("unknown kid")
    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url_decode(sig_b64), expected_sig):
        raise ValueError("invalid signature")
    payload = json.loads(_b64url_decode(payload_b64))
    if payload.get("aud") != audience:
        raise ValueError("invalid audience")
    exp = payload.get("exp")
    if exp is not None and int(exp) < int(time.time()):
        raise ValueError("token expired")
    return payload


def get_token_header(token: str) -> dict[str, Any]:
    """Return the decoded header for ``token``."""

    header_b64 = token.split(".")[0]
    return json.loads(_b64url_decode(header_b64))


def jwks(cfg: EventDescriptorConfig) -> dict[str, Any]:
    """Return a JWKS document for the configured keys."""

    keys = []
    for kid, secret in cfg.keys.items():
        keys.append(
            {
                "kty": "oct",
                "use": "sig",
                "alg": "HS256",
                "kid": kid,
                "k": _b64url_encode(secret.encode()),
            }
        )
    return {"keys": keys}


__all__ = [
    "EventDescriptorConfig",
    "sign_event_token",
    "validate_event_token",
    "get_token_header",
    "jwks",
]

