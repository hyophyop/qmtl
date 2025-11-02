"""Lightweight schema guard for fills routing invalid payloads to DLQ.

This helper is intentionally minimal and does not depend on external schema
validators. It checks for the presence and basic types of ``symbol``,
``quantity`` and either ``fill_price``/``price``.
"""

from __future__ import annotations

from typing import Any


def validate_fill_or_dlq(payload: dict) -> dict:
    try:
        sym = payload.get("symbol")
        qty = payload.get("quantity")
        price = payload.get("fill_price", payload.get("price"))
        if not isinstance(sym, str):
            raise ValueError("symbol")
        if not isinstance(qty, (int, float)):
            raise ValueError("quantity")
        if not isinstance(price, (int, float)):
            raise ValueError("price")
        return payload
    except Exception:
        return {"dlq": True, "payload": payload}


__all__ = ["validate_fill_or_dlq"]

