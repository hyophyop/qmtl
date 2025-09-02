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
import os
import time
from pathlib import Path
from typing import Any, Dict

try:  # optional
    import pyarrow as pa  # type: ignore
    import pyarrow.parquet as pq  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pa = None  # type: ignore
    pq = None  # type: ignore

try:  # optional
    import fsspec  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    fsspec = None  # type: ignore

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


def _node_key(node) -> str:
    return f"{node.node_id}"


def write_snapshot(node) -> Path | None:
    """Write a snapshot for ``node`` if cache has data.

    Returns the written snapshot path or ``None`` when nothing to write.
    """
    cache = getattr(node, "cache", None)
    if cache is None:
        return None
    # Capture current data
    data = {}
    last_ts = cache.last_timestamps()
    if not last_ts:
        return None
    for u, mp in last_ts.items():
        for interval, _ in mp.items():
            # store a bounded slice (up to period)
            items = cache.get_slice(u, interval, count=getattr(node, "period", 0))
            data.setdefault(u, {})[interval] = [
                (int(ts), _b64(json.dumps(payload).encode())) for ts, payload in items
            ]
    # Compute a state hash for validation/fallback
    state_hash: str | None = None
    try:
        state_hash = cache.input_window_hash()  # type: ignore[attr-defined]
    except Exception:
        state_hash = None

    meta: Dict[str, Any] = {
        "node_id": node.node_id,
        "interval": node.interval,
        "period": node.period,
        "schema_hash": node.schema_hash,
        "runtime_fingerprint": runtime_fingerprint(),
        "state_hash": state_hash,
        "wm_ts": int(min(
            (ts for mp in last_ts.values() for ts in mp.values() if ts is not None),
            default=0,
        )),
        "created_at": int(time.time()),
        "format": os.getenv("QMTL_SNAPSHOT_FORMAT", "json").lower(),
    }
    key = _node_key(node)
    fmt = meta["format"]
    base = _snapshot_dir()
    if fmt == "parquet" and pa is not None and pq is not None:
        # Write rows to Parquet and meta to a sidecar JSON
        rows_u: list[str] = []
        rows_i: list[int] = []
        rows_t: list[int] = []
        rows_v: list[bytes] = []
        for u, mp in data.items():
            for interval, items in mp.items():
                for ts, b64 in items:
                    rows_u.append(u)
                    rows_i.append(int(interval))
                    rows_t.append(int(ts))
                    rows_v.append(_b64d(b64))
        table = pa.table({
            "u": pa.array(rows_u, pa.string()),
            "i": pa.array(rows_i, pa.int64()),
            "t": pa.array(rows_t, pa.int64()),
            "v": pa.array(rows_v, pa.binary()),
        })
        pq_path = base / f"{key}_{meta['wm_ts']}.snap.parquet"
        start = time.perf_counter()
        pq.write_table(table, pq_path)
        meta_path = base / f"{key}_{meta['wm_ts']}.meta.json"
        meta_obj = {"meta": meta}
        with meta_path.open("w") as mf:
            json.dump(meta_obj, mf)
        duration_ms = (time.perf_counter() - start) * 1000
        path = pq_path
    else:
        # Fallback to JSON container
        path = base / f"{key}_{meta['wm_ts']}.snap.json"
        start = time.perf_counter()
        with path.open("w") as f:
            json.dump({"meta": meta, "data": data}, f)
    duration_ms = (time.perf_counter() - start) * 1000
    try:
        sdk_metrics.node_processed_total  # type: ignore[attr-defined]
        # Record snapshot metrics when available
        if hasattr(sdk_metrics, "snapshot_write_duration_ms"):
            sdk_metrics.snapshot_write_duration_ms.observe(duration_ms)  # type: ignore[attr-defined]
        if hasattr(sdk_metrics, "snapshot_bytes_total"):
            sdk_metrics.snapshot_bytes_total.inc(path.stat().st_size)  # type: ignore[attr-defined]
    except Exception:
        pass
    return path


def hydrate(node, *, strict_runtime: bool | None = None) -> bool:
    """Hydrate ``node.cache`` from the latest compatible snapshot.

    Returns ``True`` when hydration was applied, ``False`` otherwise.
    """
    strict = os.getenv("QMTL_SNAPSHOT_STRICT_RUNTIME", "0") == "1" if strict_runtime is None else strict_runtime
    key = _node_key(node)
    base = _snapshot_dir()
    # Prefer Parquet snapshots when present, fall back to JSON
    pq_candidates = sorted(base.glob(f"{key}_*.snap.parquet"), reverse=True)
    json_candidates = sorted(base.glob(f"{key}_*.snap.json"), reverse=True)
    candidates = pq_candidates + json_candidates
    if not candidates:
        return False
    for path in candidates:
        try:
            if path.suffix == ".parquet" and pa is not None and pq is not None:
                meta_path = path.with_suffix(".meta.json")
                if not meta_path.exists():
                    continue
                obj = json.loads(meta_path.read_text())
                meta = obj.get("meta", {})
                table = pq.read_table(path)
                data: Dict[str, Dict[int, list[tuple[int, Any]]]] = {}
                u_col = table.column("u").to_pylist()
                i_col = table.column("i").to_pylist()
                t_col = table.column("t").to_pylist()
                v_col = table.column("v").to_pylist()
                for u, i, t, v in zip(u_col, i_col, t_col, v_col):
                    data.setdefault(u, {}).setdefault(int(i), []).append((int(t), json.loads(v)))
            else:
                obj = json.loads(path.read_text())
                meta = obj.get("meta", {})
                data = obj.get("data", {})
            if strict and meta.get("runtime_fingerprint") != runtime_fingerprint():
                continue
            if meta.get("schema_hash") != node.schema_hash:
                continue
            # Merge into cache preserving most recent
            for u, mp in data.items():
                for interval_s, items in mp.items():
                    interval = int(interval_s)
                    decoded = []
                    for ts, b64 in items:
                        try:
                            if isinstance(b64, (bytes, bytearray)):
                                payload = json.loads(b64.decode())
                            else:
                                payload = json.loads(_b64d(b64).decode())
                        except Exception:
                            continue
                        decoded.append((int(ts), payload))
                    node.cache.backfill_bulk(u, interval, decoded)
            # Optional state hash validation
            try:
                expect_hash = meta.get("state_hash")
                cur_hash = node.cache.input_window_hash()  # type: ignore[attr-defined]
                if expect_hash and cur_hash != expect_hash:
                    # Fallback: drop hydrated state
                    for u, mp in list(node.cache.last_timestamps().items()):  # type: ignore[attr-defined]
                        for i in list(mp.keys()):
                            node.cache.drop(u, i)  # type: ignore[attr-defined]
                    if hasattr(sdk_metrics, "snapshot_hydration_fallback_total"):
                        sdk_metrics.snapshot_hydration_fallback_total.inc()  # type: ignore[attr-defined]
                    continue
            except Exception:
                pass
            if hasattr(sdk_metrics, "snapshot_hydration_success_total"):
                try:
                    sdk_metrics.snapshot_hydration_success_total.inc()  # type: ignore[attr-defined]
                except Exception:
                    pass
            return True
        except Exception:
            continue
    return False
