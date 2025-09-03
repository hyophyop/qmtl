from __future__ import annotations

"""Common helpers for TagQuery normalization shared by SDK and Gateway."""

from typing import Any, Iterable

from qmtl.sdk.node import MatchMode

__all__ = [
    "split_tags",
    "normalize_match_mode",
    "normalize_queues",
]


def split_tags(tags: str | Iterable[str] | None) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        return [t for t in tags.split(",") if t]
    return [str(t) for t in tags]


def normalize_match_mode(match_mode: str | None) -> MatchMode:
    mode_str = (match_mode or "any").lower()
    try:
        return MatchMode(mode_str)
    except ValueError:
        return MatchMode.ANY


def normalize_queues(raw: Iterable[Any]) -> list[str]:
    queues: list[str] = []
    for q in raw:
        if isinstance(q, dict):
            if q.get("global"):
                continue
            # Only accept unified 'queue' key; legacy 'topic' is not supported
            val = q.get("queue")
            if val:
                queues.append(str(val))
        else:
            queues.append(str(q))
    return queues
