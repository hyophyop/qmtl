from __future__ import annotations

from dataclasses import dataclass
import json
import time
import base64
import hmac
import hashlib
from typing import Any


@dataclass
class EventDescriptorConfig:
    secret: str
    kid: str
    ttl: int = 300
    stream_url: str = "wss://gateway/ws/evt"
    fallback_url: str = "wss://gateway/ws/fallback"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def sign_event_token(claims: dict[str, Any], cfg: EventDescriptorConfig) -> str:
    header = {"alg": "HS256", "typ": "JWT", "kid": cfg.kid}
    header_b64 = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode()
    )
    payload_b64 = _b64url_encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    )
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(cfg.secret.encode(), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def validate_event_token(
    token: str, cfg: EventDescriptorConfig, audience: str = "controlbus"
) -> dict[str, Any]:
    header_b64, payload_b64, sig_b64 = token.split(".")
    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(cfg.secret.encode(), signing_input, hashlib.sha256).digest()
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
    header_b64 = token.split(".")[0]
    return json.loads(_b64url_decode(header_b64))
