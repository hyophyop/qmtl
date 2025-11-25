"""Canonical dataset fingerprint helpers for artifact publication."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence
import hashlib
import json

import pandas as pd

__all__ = [
    "compute_artifact_fingerprint",
]


_CANONICAL_PREFIX = "sha256:"


def _canonicalize_value(value: Any) -> Any:
    if isinstance(value, (int, float, str, bool)):
        return value
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return int(value.value // 10**9)
    if isinstance(value, pd.Timedelta):
        return int(value.value // 10**9)
    if pd.isna(value):
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


def _canonicalize_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []

    working = frame.copy()
    if "ts" in working.columns:
        working["ts"] = pd.to_numeric(working["ts"], errors="coerce").astype("Int64")
        working.dropna(subset=["ts"], inplace=True)
        working["ts"] = working["ts"].astype("int64")
        working.sort_values("ts", inplace=True)
    else:
        working.sort_index(inplace=True)
    working.reset_index(drop=True, inplace=True)

    columns = _canonicalize_columns(list(working.columns))
    records: list[dict[str, Any]] = []
    for _, row in working[columns].iterrows():
        record = {col: _canonicalize_value(row[col]) for col in columns}
        records.append(record)
    return records


def _serialize_payload(frame: pd.DataFrame, metadata: Mapping[str, Any], *, sort_metadata: bool) -> bytes:
    payload = {
        "frame": _canonicalize_frame(frame),
        "metadata": _normalize_metadata(metadata, sort_keys=sort_metadata),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_artifact_fingerprint(frame: pd.DataFrame, metadata: Mapping[str, Any]) -> str:
    """Return the canonical ``sha256:<digest>`` fingerprint for *frame* and *metadata*."""

    serialized = _serialize_payload(frame, metadata, sort_metadata=True)
    digest = hashlib.sha256(serialized).hexdigest()
    return f"{_CANONICAL_PREFIX}{digest}"
