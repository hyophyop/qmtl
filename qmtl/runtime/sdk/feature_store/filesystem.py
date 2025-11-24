from __future__ import annotations

"""Filesystem-backed Feature Artifact storage."""

import base64
import json
import os
import pickle
import threading
from pathlib import Path
from typing import Any, Iterable

from .base import FeatureArtifactKey, FeatureStoreBackend


def _sanitize_component(value: str) -> str:
    value = value.strip()
    if not value:
        return "_"
    banned = {"/", "\\", ".."}
    if value in banned:
        return "_"
    return "".join(c if c.isalnum() or c in {"-", "_", "."} else "_" for c in value)


class FileSystemFeatureStore(FeatureStoreBackend):
    """Simple JSONL + pickle filesystem implementation."""

    def __init__(self, base_dir: str | os.PathLike[str], *, max_versions: int | None = None) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_versions = max_versions
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def _artifact_dir(self, key: FeatureArtifactKey) -> Path:
        parts = [
            _sanitize_component(key.factor),
            _sanitize_component(key.dataset_fingerprint),
            _sanitize_component(key.params),
            _sanitize_component(key.instrument),
            str(int(key.interval)),
        ]
        path = self.base_dir.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _payload_to_record(self, key: FeatureArtifactKey, payload: Any) -> dict[str, Any]:
        blob = pickle.dumps(payload)
        encoded = base64.b64encode(blob).decode()
        return {
            "t": int(key.timestamp),
            "version": int(key.version),
            "payload": encoded,
        }

    def _read_records(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            records.append(obj)
        return records

    def _write_records(self, path: Path, records: list[dict[str, Any]]) -> None:
        payload = "\n".join(json.dumps(r, sort_keys=True) for r in records)
        path.write_text(payload + ("\n" if payload else ""))

    def _enforce_retention(self, path: Path) -> None:
        if self.max_versions is None:
            return
        records = self._read_records(path)
        if len(records) <= self.max_versions:
            return
        ordered = sorted(records, key=lambda r: r.get("t", 0))
        keep = ordered[-self.max_versions :]
        self._write_records(path, keep)

    # ------------------------------------------------------------------
    def write(self, key: FeatureArtifactKey, payload: Any) -> None:
        target_dir = self._artifact_dir(key)
        file_path = target_dir / "artifacts.jsonl"
        record = self._payload_to_record(key, payload)
        with self._lock:
            existing = self._read_records(file_path)
            existing.append(record)
            existing.sort(key=lambda r: r.get("t", 0))
            self._write_records(file_path, existing)
            self._enforce_retention(file_path)

    def load_series(
        self,
        *,
        factor: str,
        interval: int,
        params: str,
        instrument: str,
        dataset_fingerprint: str,
        start: int | None = None,
        end: int | None = None,
    ) -> list[tuple[int, Any]]:
        key = FeatureArtifactKey(
            factor=factor,
            interval=interval,
            params=params,
            instrument=instrument,
            timestamp=0,
            dataset_fingerprint=dataset_fingerprint,
        )
        file_path = self._artifact_dir(key) / "artifacts.jsonl"
        records = self._read_records(file_path)
        results: list[tuple[int, Any]] = []
        for rec in records:
            try:
                ts_raw = rec.get("t")
                if ts_raw is None:
                    continue
                ts = int(ts_raw)
            except (TypeError, ValueError):
                continue
            if start is not None and ts < start:
                continue
            if end is not None and ts > end:
                continue
            payload_raw = rec.get("payload")
            if not isinstance(payload_raw, str):
                continue
            try:
                payload = pickle.loads(base64.b64decode(payload_raw))
            except Exception:
                continue
            results.append((ts, payload))
        results.sort(key=lambda item: item[0])
        return results

    def list_instruments(
        self,
        *,
        factor: str,
        params: str,
        dataset_fingerprint: str,
    ) -> Iterable[str]:
        base = self.base_dir / _sanitize_component(factor) / _sanitize_component(dataset_fingerprint) / _sanitize_component(params)
        if not base.exists():
            return []
        return [p.name for p in base.iterdir() if p.is_dir()]

    def count(
        self,
        *,
        factor: str,
        interval: int,
        params: str,
        instrument: str,
        dataset_fingerprint: str,
    ) -> int:
        key = FeatureArtifactKey(
            factor=factor,
            interval=interval,
            params=params,
            instrument=instrument,
            timestamp=0,
            dataset_fingerprint=dataset_fingerprint,
        )
        file_path = self._artifact_dir(key) / "artifacts.jsonl"
        return len(self._read_records(file_path))
