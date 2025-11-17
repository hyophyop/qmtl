from __future__ import annotations

"""Lightweight snapshot/hydration helpers for Node caches.

This module implements a pragmatic baseline for P0‑4 (Snapshot checkpointing
and state hydration). It stores per‑node cache snapshots to the local
filesystem and hydrates them on startup to shorten warmup. In production, the
same interfaces can be backed by S3/MinIO via fsspec.

Environment variables:
- QMTL_SNAPSHOT_DIR: base directory for snapshots (default: .qmtl_snapshots)
- QMTL_SNAPSHOT_STRICT_RUNTIME: '1' to require matching runtime fingerprint
"""

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Mapping, NamedTuple, Protocol, Tuple

logger = logging.getLogger(__name__)


def _get_arrow_context() -> ArrowContext | None:
    try:  # optional
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:  # pragma: no cover - optional dependency
        return None
    except Exception:  # pragma: no cover - optional dependency
        logger.exception("unexpected error importing pyarrow")
        return None
    return ArrowContext(pa=pa, parquet=pq)


def _get_filesystem(url: str | None) -> tuple[str | None, FileSystemLike | None]:
    if not url:
        return None, None
    try:  # optional
        import fsspec
    except ImportError:  # pragma: no cover - optional dependency
        return None, None
    except Exception:  # pragma: no cover - optional dependency
        logger.exception("unexpected error importing fsspec")
        return None, None
    try:
        fs, _, paths = fsspec.get_fs_token_paths(url)
        base = paths[0] if paths else url
        return (base, fs)
    except Exception:
        return None, None


class ArrowTableWriter(Protocol):
    """Subset of the pyarrow.parquet API used by this module."""

    def write_table(self, table: Any, where: Any) -> Any:  # pragma: no cover - protocol signature
        ...

    def read_table(self, source: Any) -> Any:  # pragma: no cover - protocol signature
        ...


class FileSystemLike(Protocol):
    """Minimal filesystem interface used for remote snapshots."""

    def open(self, path: str, mode: str = ...) -> Any:  # pragma: no cover - protocol signature
        ...

    def glob(self, path: str) -> list[Any]:  # pragma: no cover - protocol signature
        ...


class ArrowContext(NamedTuple):
    pa: Any
    parquet: ArrowTableWriter

from . import metrics as sdk_metrics


def _b64(obj: Any) -> str:
    return base64.b64encode(obj).decode()


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode())


def runtime_fingerprint() -> str:
    """Return a coarse runtime fingerprint string.

    Includes python version, qmtl version (if available), numpy version (if
    installed), os info. The intent is to gate reuse across materially different
    environments without causing excessive churn.
    """
    import sys
    import platform

    parts = [
        f"python={sys.version_info.major}.{sys.version_info.minor}",
        f"os={platform.system().lower()}-{platform.machine().lower()}",
    ]
    try:
        import qmtl  # type: ignore

        ver = getattr(qmtl, "__version__", None) or "0"
        parts.append(f"qmtl={ver}")
    except Exception:
        parts.append("qmtl=0")
    try:
        import numpy as _np  # type: ignore

        parts.append(f"numpy={_np.__version__}")
    except Exception:
        parts.append("numpy=0")
    return ";".join(parts)


def _snapshot_dir() -> Path:
    base = os.getenv("QMTL_SNAPSHOT_DIR", ".qmtl_snapshots")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _remote_base() -> Tuple[str | None, FileSystemLike | None]:
    """Return (base_url, filesystem) when remote snapshots are configured.

    Uses ``QMTL_SNAPSHOT_URL`` (e.g. ``s3://bucket/prefix``). Returns ``(None, None)``
    when not configured or when ``fsspec`` is unavailable.
    """
    url = os.getenv("QMTL_SNAPSHOT_URL")
    return _get_filesystem(url)


def _node_key(node) -> str:
    return f"{node.node_id}"


def write_snapshot(node) -> Path | None:
    """Write a snapshot for ``node`` if cache has data.

    Returns the written snapshot path or ``None`` when nothing to write.
    """

    cache = getattr(node, "cache", None)
    if cache is None:
        return None

    last_ts = cache.last_timestamps()
    if not last_ts:
        return None

    data = _collect_snapshot_payload(cache, node, last_ts)
    state_hash = _compute_state_hash(cache)
    meta = _build_snapshot_meta(node, last_ts, state_hash)

    key = _node_key(node)
    remote_url, filesystem = _remote_base()
    arrow = _get_arrow_context()
    base_dir = _snapshot_dir()

    start = time.perf_counter()
    if _should_use_parquet(meta["format"], arrow):
        assert arrow is not None
        path_obj = _write_parquet_snapshot(
            data=data,
            meta=meta,
            key=key,
            remote_url=remote_url,
            filesystem=filesystem,
            base_dir=base_dir,
            arrow=arrow,
        )
    else:
        path_obj = _write_json_snapshot(
            data=data,
            meta=meta,
            key=key,
            remote_url=remote_url,
            filesystem=filesystem,
            base_dir=base_dir,
        )
    duration_ms = (time.perf_counter() - start) * 1000

    _record_snapshot_metrics(path_obj, duration_ms)
    return path_obj


def _collect_snapshot_payload(cache, node, last_ts: Mapping[str, Mapping[Any, Any]]) -> Dict[str, Dict[int, list[tuple[int, str]]]]:
    data: Dict[str, Dict[int, list[tuple[int, str]]]] = {}
    for universe, interval_map in last_ts.items():
        for interval in interval_map.keys():
            items = cache.get_slice(universe, interval, count=getattr(node, "period", 0))
            encoded_items = [
                (int(ts), _b64(json.dumps(payload).encode()))
                for ts, payload in items
            ]
            data.setdefault(universe, {})[int(interval)] = encoded_items
    return data


def _compute_state_hash(cache) -> str | None:
    try:
        return cache.input_window_hash()  # type: ignore[attr-defined]
    except Exception:
        return None


def _build_snapshot_meta(
    node,
    last_ts: Mapping[str, Mapping[Any, Any]],
    state_hash: str | None,
) -> Dict[str, Any]:
    wm_ts = int(
        min(
            (ts for mp in last_ts.values() for ts in mp.values() if ts is not None),
            default=0,
        )
    )
    meta: Dict[str, Any] = {
        "node_id": node.node_id,
        "interval": node.interval,
        "period": node.period,
        "schema_hash": node.schema_hash,
        "schema_compat_id": getattr(node, "schema_compat_id", None),
        "runtime_fingerprint": runtime_fingerprint(),
        "state_hash": state_hash,
        "wm_ts": wm_ts,
        "created_at": int(time.time()),
        "format": os.getenv("QMTL_SNAPSHOT_FORMAT", "json").lower(),
    }
    dataset_fp = getattr(node, "dataset_fingerprint", None)
    if dataset_fp:
        meta["dataset_fingerprint"] = str(dataset_fp)
    return meta


def _should_use_parquet(fmt: str, arrow: ArrowContext | None) -> bool:
    return fmt == "parquet" and arrow is not None


def _write_parquet_snapshot(
    *,
    data: Dict[str, Dict[int, list[tuple[int, str]]]],
    meta: Dict[str, Any],
    key: str,
    remote_url: str | None,
    filesystem: FileSystemLike | None,
    base_dir: Path,
    arrow: ArrowContext,
):
    rows_u: list[str] = []
    rows_i: list[int] = []
    rows_t: list[int] = []
    rows_v: list[bytes] = []
    for universe, interval_map in data.items():
        for interval, items in interval_map.items():
            for ts, encoded in items:
                rows_u.append(universe)
                rows_i.append(int(interval))
                rows_t.append(int(ts))
                rows_v.append(_b64d(encoded))
    table = arrow.pa.table({
        "u": arrow.pa.array(rows_u, arrow.pa.string()),
        "i": arrow.pa.array(rows_i, arrow.pa.int64()),
        "t": arrow.pa.array(rows_t, arrow.pa.int64()),
        "v": arrow.pa.array(rows_v, arrow.pa.binary()),
    })

    if remote_url and filesystem is not None:
        pq_path = f"{remote_url.rstrip('/')}/{key}_{meta['wm_ts']}.snap.parquet"
        with filesystem.open(pq_path, "wb") as handle:
            arrow.parquet.write_table(table, handle)
        meta_path = f"{remote_url.rstrip('/')}/{key}_{meta['wm_ts']}.meta.json"
        with filesystem.open(meta_path, "w") as meta_handle:
            json.dump({"meta": meta}, meta_handle)
        return Path(pq_path) if not isinstance(pq_path, Path) else pq_path

    pq_path = base_dir / f"{key}_{meta['wm_ts']}.snap.parquet"
    arrow.parquet.write_table(table, pq_path)
    meta_path = base_dir / f"{key}_{meta['wm_ts']}.meta.json"
    with meta_path.open("w") as meta_handle:
        json.dump({"meta": meta}, meta_handle)
    return pq_path


def _write_json_snapshot(
    *,
    data: Dict[str, Dict[int, list[tuple[int, str]]]],
    meta: Dict[str, Any],
    key: str,
    remote_url: str | None,
    filesystem: FileSystemLike | None,
    base_dir: Path,
):
    if remote_url and filesystem is not None:
        path = f"{remote_url.rstrip('/')}/{key}_{meta['wm_ts']}.snap.json"
        with filesystem.open(path, "w") as handle:
            json.dump({"meta": meta, "data": data}, handle)
        return Path(path) if not isinstance(path, Path) else path

    path = base_dir / f"{key}_{meta['wm_ts']}.snap.json"
    with path.open("w") as handle:
        json.dump({"meta": meta, "data": data}, handle)
    return path


def _record_snapshot_metrics(path: Path | str, duration_ms: float) -> None:
    try:
        sdk_metrics.node_processed_total  # type: ignore[attr-defined]
        if hasattr(sdk_metrics, "snapshot_write_duration_ms"):
            sdk_metrics.snapshot_write_duration_ms.observe(duration_ms)  # type: ignore[attr-defined]
        if hasattr(sdk_metrics, "snapshot_bytes_total"):
            size = None
            if isinstance(path, Path):
                if path.exists():
                    size = path.stat().st_size
            elif hasattr(path, "stat"):
                size = path.stat().st_size  # type: ignore[attr-defined]
            elif isinstance(path, str):
                candidate = Path(path)
                if candidate.exists():
                    size = candidate.stat().st_size
            if size is not None:
                sdk_metrics.snapshot_bytes_total.inc(size)  # type: ignore[attr-defined]
    except Exception:
        pass



def hydrate(node, *, strict_runtime: bool | None = None) -> bool:
    """Hydrate ``node.cache`` from the latest compatible snapshot.

    Returns ``True`` when hydration was applied, ``False`` otherwise.
    """
    strict = (
        os.getenv("QMTL_SNAPSHOT_STRICT_RUNTIME", "0") == "1"
        if strict_runtime is None
        else strict_runtime
    )
    remote_url, fs = _remote_base()
    arrow = _get_arrow_context()
    candidates = _snapshot_candidates(
        key=_node_key(node),
        base_dir=_snapshot_dir(),
        remote_url=remote_url,
        filesystem=fs,
    )
    if not candidates:
        return False
    for path in candidates:
        try:
            payload = _load_snapshot_payload(path, remote_url, fs, arrow)
        except Exception:
            continue
        if payload is None:
            continue
        meta, data = payload
        if not _is_snapshot_compatible(meta, node, strict):
            continue
        try:
            _apply_snapshot_data(node, data)
        except Exception:
            continue
        if not _validate_state_hash(node, meta):
            _handle_hydration_fallback(node)
            continue
        _record_hydration_success()
        return True
    return False


def _snapshot_candidates(
    *,
    key: str,
    base_dir: Path,
    remote_url: str | None,
    filesystem: FileSystemLike | None,
) -> list[Any]:
    pq_candidates: list[Any] = []
    json_candidates: list[Any] = []
    if remote_url and filesystem is not None:
        try:
            pq_candidates = sorted(
                filesystem.glob(f"{remote_url.rstrip('/')}/{key}_*.snap.parquet"),
                reverse=True,
            )
            json_candidates = sorted(
                filesystem.glob(f"{remote_url.rstrip('/')}/{key}_*.snap.json"),
                reverse=True,
            )
        except Exception:
            return []
    else:
        pq_candidates = sorted(base_dir.glob(f"{key}_*.snap.parquet"), reverse=True)
        json_candidates = sorted(base_dir.glob(f"{key}_*.snap.json"), reverse=True)
    return pq_candidates + json_candidates


def _load_snapshot_payload(
    path: Any,
    remote_url: str | None,
    filesystem: FileSystemLike | None,
    arrow: ArrowContext | None,
) -> tuple[Dict[str, Any], Dict[str, Any]] | None:
    if _is_parquet_path(path):
        return _load_parquet_payload(path, remote_url, filesystem, arrow)
    return _load_json_payload(path, remote_url, filesystem)


def _is_parquet_path(path: Any) -> bool:
    if isinstance(path, str):
        return path.endswith(".parquet")
    if isinstance(path, Path):
        return path.suffix == ".parquet"
    return False


def _load_parquet_payload(
    path: Any,
    remote_url: str | None,
    filesystem: FileSystemLike | None,
    arrow: ArrowContext | None,
) -> tuple[Dict[str, Any], Dict[str, Any]] | None:
    if arrow is None:
        return None
    meta = _read_parquet_meta(path, remote_url, filesystem)
    if meta is None:
        return None
    if remote_url and filesystem is not None and isinstance(path, str):
        with filesystem.open(path, "rb") as handle:
            table = arrow.parquet.read_table(handle)
    else:
        table = arrow.parquet.read_table(path)
    data: Dict[str, Dict[int, list[tuple[int, Any]]]] = {}
    for u, i, t, v in zip(
        table.column("u").to_pylist(),
        table.column("i").to_pylist(),
        table.column("t").to_pylist(),
        table.column("v").to_pylist(),
    ):
        data.setdefault(u, {}).setdefault(int(i), []).append((int(t), v))
    return meta, data


def _read_parquet_meta(
    path: Any,
    remote_url: str | None,
    filesystem: FileSystemLike | None,
) -> Dict[str, Any] | None:
    if remote_url and filesystem is not None and isinstance(path, str):
        meta_path = path.replace(".snap.parquet", ".meta.json")
        try:
            with filesystem.open(meta_path, "r") as handle:
                obj = json.load(handle)
        except Exception:
            return None
        return obj.get("meta", {})
    meta_path = Path(path).with_suffix(".meta.json")
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text()).get("meta", {})


def _load_json_payload(
    path: Any,
    remote_url: str | None,
    filesystem: FileSystemLike | None,
) -> tuple[Dict[str, Any], Dict[str, Any]] | None:
    if remote_url and filesystem is not None and isinstance(path, str):
        with filesystem.open(path, "r") as handle:
            obj = json.load(handle)
    else:
        text = Path(path).read_text() if isinstance(path, (str, Path)) else path.read_text()
        obj = json.loads(text)
    meta = obj.get("meta", {})
    data = obj.get("data", {})
    return meta, data


def _is_snapshot_compatible(meta: Mapping[str, Any], node, strict: bool) -> bool:
    if strict and meta.get("runtime_fingerprint") != runtime_fingerprint():
        return False
    if meta.get("schema_hash") != node.schema_hash:
        return False
    expected_df = getattr(node, "dataset_fingerprint", None)
    if expected_df:
        snap_df = meta.get("dataset_fingerprint")
        if snap_df != expected_df:
            return False
    return True


def _apply_snapshot_data(node, data: Mapping[str, Any]) -> None:
    cache = getattr(node, "cache", None)
    if cache is None:
        return
    for universe, interval_map in data.items():
        if not isinstance(interval_map, Mapping):
            continue
        for interval_key, items in interval_map.items():
            interval = int(interval_key)
            decoded: list[tuple[int, Any]] = []
            for ts, payload in items:
                decoded_payload = _decode_snapshot_payload(payload)
                if decoded_payload is None:
                    continue
                decoded.append((int(ts), decoded_payload))
            if decoded:
                cache.backfill_bulk(universe, interval, decoded)


def _decode_snapshot_payload(payload: Any) -> Any:
    if isinstance(payload, (dict, list)) or payload is None:
        return payload
    if isinstance(payload, (int, float)):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        try:
            return json.loads(payload.decode())
        except Exception:
            return None
    if isinstance(payload, str):
        try:
            return json.loads(_b64d(payload).decode())
        except Exception:
            return payload
    return None


def _validate_state_hash(node, meta: Mapping[str, Any]) -> bool:
    try:
        expected = meta.get("state_hash")
        if not expected:
            return True
        cache = getattr(node, "cache", None)
        if cache is None:
            return True
        current = cache.input_window_hash()  # type: ignore[attr-defined]
        return current == expected
    except Exception:
        return True


def _handle_hydration_fallback(node) -> None:
    cache = getattr(node, "cache", None)
    if cache is None:
        return
    try:
        last_ts = cache.last_timestamps()  # type: ignore[attr-defined]
    except Exception:
        last_ts = {}
    items = last_ts.items() if hasattr(last_ts, "items") else []
    for universe, intervals in list(items):
        interval_keys = intervals.keys() if hasattr(intervals, "keys") else []
        for interval in list(interval_keys):
            try:
                cache.drop(universe, interval)  # type: ignore[attr-defined]
            except Exception:
                continue
    if hasattr(sdk_metrics, "snapshot_hydration_fallback_total"):
        try:
            sdk_metrics.snapshot_hydration_fallback_total.inc()  # type: ignore[attr-defined]
        except Exception:
            pass


def _record_hydration_success() -> None:
    if hasattr(sdk_metrics, "snapshot_hydration_success_total"):
        try:
            sdk_metrics.snapshot_hydration_success_total.inc()  # type: ignore[attr-defined]
        except Exception:
            pass
