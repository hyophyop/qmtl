from __future__ import annotations

from typing import Any

from qmtl.foundation.common.tagquery import split_tags


def extract_message_payload(
    message: Any, *, expected_version: int = 1
) -> tuple[str | None, dict[str, Any]] | None:
    if not isinstance(message, dict):
        return None
    payload = message.get("data", message)
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != expected_version:
        return None
    event = message.get("event") or message.get("type")
    return event, payload


def normalize_tags(raw: Any) -> tuple[str, ...]:
    tags = raw if raw is not None else []
    return tuple(split_tags(tags))


def normalize_interval(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
