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
    meta: Dict[str, Any] = {
        "node_id": node.node_id,
        "interval": node.interval,
        "period": node.period,
        "schema_hash": node.schema_hash,
        "runtime_fingerprint": runtime_fingerprint(),
        "wm_ts": int(min(
            (ts for mp in last_ts.values() for ts in mp.values() if ts is not None),
            default=0,
        )),
        "created_at": int(time.time()),
        "format": "json-b64",
    }
    key = _node_key(node)
    path = _snapshot_dir() / f"{key}_{meta['wm_ts']}.snap.json"
    with path.open("w") as f:
        json.dump({"meta": meta, "data": data}, f)
    return path


def hydrate(node, *, strict_runtime: bool | None = None) -> bool:
    """Hydrate ``node.cache`` from the latest compatible snapshot.

    Returns ``True`` when hydration was applied, ``False`` otherwise.
    """
    strict = os.getenv("QMTL_SNAPSHOT_STRICT_RUNTIME", "0") == "1" if strict_runtime is None else strict_runtime
    key = _node_key(node)
    base = _snapshot_dir()
    candidates = sorted(base.glob(f"{key}_*.snap.json"), reverse=True)
    if not candidates:
        return False
    for path in candidates:
        try:
            obj = json.loads(path.read_text())
            meta = obj.get("meta", {})
            if strict and meta.get("runtime_fingerprint") != runtime_fingerprint():
                continue
            if meta.get("schema_hash") != node.schema_hash:
                continue
            data = obj.get("data", {})
            # Merge into cache preserving most recent
            for u, mp in data.items():
                for interval_s, items in mp.items():
                    interval = int(interval_s)
                    decoded = []
                    for ts, b64 in items:
                        try:
                            payload = json.loads(_b64d(b64).decode())
                        except Exception:
                            continue
                        decoded.append((int(ts), payload))
                    node.cache.backfill_bulk(u, interval, decoded)
            return True
        except Exception:
            continue
    return False

