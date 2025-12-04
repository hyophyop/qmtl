from __future__ import annotations

"""Common helpers for TagQuery normalization shared by SDK and Gateway."""

from enum import Enum
from typing import Any, Iterable, Mapping

__all__ = [
    "MatchMode",
    "split_tags",
    "normalize_match_mode",
    "normalize_queues",
    "canonical_tag_query_params",
    "canonical_tag_query_params_from_node",
]


class MatchMode(str, Enum):
    """Tag matching behaviour for tag query nodes."""

    ANY = "any"
    ALL = "all"


def split_tags(tags: str | Iterable[str] | None) -> list[str]:
    """Normalize a raw ``tags`` payload into a list of tag strings."""

    if tags is None:
        return []
    if isinstance(tags, str):
        return [segment for segment in (part.strip() for part in tags.split(",")) if segment]
    normalized: list[str] = []
    for item in tags:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def normalize_match_mode(match_mode: str | None) -> MatchMode:
    mode_str = (match_mode or "any").lower()
    try:
        return MatchMode(mode_str)
    except ValueError:
        return MatchMode.ANY


def normalize_queues(raw: Iterable[Any]) -> list[str]:
    queues: list[str] = []
    for q in raw:
        if not isinstance(q, dict):
            raise TypeError("queue descriptors must be objects")
        if q.get("global"):
            continue
        val = q.get("queue")
        if not val:
            raise ValueError("queue descriptor missing 'queue'")
        queues.append(str(val))
    return queues


def canonical_tag_query_params(
    tags: Iterable[str] | str | None,
    *,
    interval: Any,
    match_mode: MatchMode | str | None,
    require_tags: bool = False,
    require_interval: bool = False,
) -> dict[str, Any]:
    """Return a canonical TagQuery spec used for deterministic NodeIDs.

    Parameters
    ----------
    tags:
        Raw tag list or comma-separated string.
    interval:
        Interval value associated with the query. Coerced to ``int`` when possible.
    match_mode:
        Requested match mode; defaults to ``MatchMode.ANY`` when falsy.
    require_tags:
        If ``True``, raise ``ValueError`` when no tags remain after normalization.
    require_interval:
        If ``True``, raise ``ValueError`` when ``interval`` cannot be coerced.
    """

    normalized_tags = split_tags(tags)
    deduped = sorted({tag for tag in normalized_tags})
    if require_tags and not deduped:
        raise ValueError("TagQuery requires at least one tag")

    try:
        interval_val = int(interval) if interval is not None else None
    except Exception:
        interval_val = None
    if require_interval and interval_val is None:
        raise ValueError("TagQuery interval is required")

    return {
        "query_tags": deduped,
        "match_mode": normalize_match_mode(
            match_mode.value if isinstance(match_mode, MatchMode) else match_mode
        ).value,
        "interval": interval_val,
    }


def canonical_tag_query_params_from_node(
    node: Mapping[str, Any],
    *,
    require_tags: bool = False,
    require_interval: bool = False,
) -> dict[str, Any]:
    """Extract and canonicalize TagQuery parameters from a node mapping."""

    params_source = node.get("params")
    tags: Any = None
    match_mode: Any = None
    interval: Any = node.get("interval")

    if isinstance(params_source, Mapping):
        tags = params_source.get("query_tags") or params_source.get("tags")
        match_mode = params_source.get("match_mode")
        if interval is None and "interval" in params_source:
            interval = params_source.get("interval")

    if tags is None:
        tags = node.get("tags")
    if match_mode is None:
        match_mode = node.get("match_mode")

    return canonical_tag_query_params(
        tags,
        interval=interval,
        match_mode=match_mode,
        require_tags=require_tags,
        require_interval=require_interval,
    )
