"""Canonical dataset fingerprint helpers for artifact publication."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence
import hashlib
import json
import math
from datetime import datetime, date, timedelta

import numpy as np
import polars as pl

__all__ = [
    "compute_artifact_fingerprint",
]


_CANONICAL_PREFIX = "sha256:"


def _canonicalize_value(value: Any) -> Any:
    if isinstance(value, (int, float, str, bool)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return value
    if value is None:
        return None
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, date):
        return int(datetime(value.year, value.month, value.day).timestamp())
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    if isinstance(value, (np.datetime64, np.timedelta64)):
        return int(value.astype("int64") // 10**9)
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # pragma: no cover - defensive fallback
            pass
    return str(value)


def _iter_metadata_items(metadata: Mapping[str, Any], *, sort_keys: bool) -> Iterable[tuple[str, Any]]:
    if sort_keys:
        return ((key, metadata[key]) for key in sorted(metadata))
    return metadata.items()


def _normalize_metadata(metadata: Mapping[str, Any], *, sort_keys: bool) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in _iter_metadata_items(metadata, sort_keys=sort_keys):
        if isinstance(value, Mapping):
            normalized[key] = _normalize_metadata(value, sort_keys=sort_keys)
        elif isinstance(value, (list, tuple, set)):
            normalized[key] = [_canonicalize_value(v) for v in value]
        else:
            normalized[key] = _canonicalize_value(value)
    return normalized


def _canonicalize_columns(columns: Sequence[str]) -> list[str]:
    if "ts" in columns:
        remainder = [col for col in columns if col != "ts"]
        remainder.sort()
        return ["ts", *remainder]
    ordered = list(columns)
    ordered.sort()
    return ordered


def _canonicalize_frame(frame: pl.DataFrame) -> list[dict[str, Any]]:
    if frame.is_empty():
        return []

    working = frame.clone()
    if "ts" in working.columns:
        working = working.with_columns(pl.col("ts").cast(pl.Int64, strict=False))
        working = working.filter(pl.col("ts").is_not_null())
        working = working.sort("ts")

    columns = _canonicalize_columns(list(working.columns))
    records: list[dict[str, Any]] = []
    for row in working.select(columns).iter_rows(named=True):
        record = {col: _canonicalize_value(row[col]) for col in columns}
        records.append(record)
    return records


def _serialize_payload(frame: pl.DataFrame, metadata: Mapping[str, Any], *, sort_metadata: bool) -> bytes:
    payload = {
        "frame": _canonicalize_frame(frame),
        "metadata": _normalize_metadata(metadata, sort_keys=sort_metadata),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_artifact_fingerprint(frame: pl.DataFrame, metadata: Mapping[str, Any]) -> str:
    """Return the canonical ``sha256:<digest>`` fingerprint for *frame* and *metadata*."""

    serialized = _serialize_payload(frame, metadata, sort_metadata=True)
    digest = hashlib.sha256(serialized).hexdigest()
    return f"{_CANONICAL_PREFIX}{digest}"
