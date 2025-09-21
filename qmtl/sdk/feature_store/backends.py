from __future__ import annotations

"""Storage backends for the Feature Artifact Plane."""

import base64
import json
import os
import pickle
import re
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

try:  # optional dependency
    import fsspec  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    fsspec = None  # type: ignore

from .types import FeatureArtifact, FeatureArtifactKey


class FeatureArtifactBackend(Protocol):
    """Protocol implemented by artifact storage backends."""

    def list_versions(self, key: FeatureArtifactKey) -> list[int]:
        ...

    def write(self, artifact: FeatureArtifact) -> FeatureArtifact:
        ...

    def read(self, key: FeatureArtifactKey, version: int) -> FeatureArtifact | None:
        ...

    def delete(self, key: FeatureArtifactKey, version: int) -> None:
        ...


def _sanitize(component: str) -> str:
    component = component.strip()
    component = component.replace(os.sep, "_")
    component = re.sub(r"[^A-Za-z0-9_.=-]", "_", component)
    return component or "_"


def _params_hash(key: FeatureArtifactKey) -> str:
    import hashlib

    return hashlib.blake2b(key.params.encode("utf-8"), digest_size=16).hexdigest()


class LocalFileArtifactBackend:
    """Persist artifacts on the local filesystem."""

    def __init__(self, base_path: str | Path | None = None) -> None:
        root = Path(base_path or os.getenv("QMTL_FEATURE_STORE_DIR", ".qmtl_feature_store"))
        root.mkdir(parents=True, exist_ok=True)
        self._base = root

    # Helpers -----------------------------------------------------------------
    def _dir(self, key: FeatureArtifactKey) -> Path:
        parts = [
            _sanitize(key.factor),
            f"interval={key.interval}",
            _sanitize(key.instrument),
            f"params={_params_hash(key)}",
            _sanitize(key.dataset_fingerprint),
            f"ts={int(key.timestamp)}",
        ]
        path = self._base.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _path(self, key: FeatureArtifactKey, version: int) -> Path:
        return self._dir(key) / f"v{version:06d}.json"

    # API ---------------------------------------------------------------------
    def list_versions(self, key: FeatureArtifactKey) -> list[int]:
        folder = self._dir(key)
        versions: list[int] = []
        for child in folder.glob("v*.json"):
            try:
                versions.append(int(child.stem[1:]))
            except ValueError:
                continue
        return sorted(versions)

    def write(self, artifact: FeatureArtifact) -> FeatureArtifact:
        path = self._path(artifact.key, artifact.version)
        payload_block: dict[str, Any]
        encoding = "json"
        try:
            json.dumps(artifact.payload)
            payload_block = {"encoding": "json", "value": artifact.payload}
        except TypeError:
            data = base64.b64encode(pickle.dumps(artifact.payload)).decode("ascii")
            payload_block = {"encoding": "pickle", "value": data}
            encoding = "pickle"
        payload = {
            "key": artifact.key.as_dict(),
            "meta": {
                "version": artifact.version,
                "created_at": artifact.created_at,
                "execution_domain": artifact.execution_domain,
                "world_id": artifact.world_id,
                "encoding": encoding,
            },
            "payload": payload_block,
        }
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        tmp.replace(path)
        return replace(artifact, encoding=encoding)

    def read(self, key: FeatureArtifactKey, version: int) -> FeatureArtifact | None:
        path = self._path(key, version)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        payload_block = raw.get("payload", {})
        encoding = payload_block.get("encoding", "json")
        if encoding == "pickle":
            payload = pickle.loads(base64.b64decode(payload_block.get("value", "")))
        else:
            payload = payload_block.get("value")
        meta = raw.get("meta", {})
        created_at = float(meta.get("created_at", time.time()))
        return FeatureArtifact(
            key=key,
            version=version,
            payload=payload,
            created_at=created_at,
            execution_domain=str(meta.get("execution_domain", "unknown")),
            world_id=meta.get("world_id"),
            encoding=str(encoding),
        )

    def delete(self, key: FeatureArtifactKey, version: int) -> None:
        path = self._path(key, version)
        try:
            path.unlink()
        except FileNotFoundError:  # pragma: no cover - benign race
            return


class ObjectStoreArtifactBackend(LocalFileArtifactBackend):
    """Optional backend persisting artifacts via ``fsspec``."""

    def __init__(self, base_url: str, *, cache_dir: str | Path | None = None) -> None:
        if fsspec is None:  # pragma: no cover - optional dependency guard
            raise RuntimeError("fsspec is required for ObjectStoreArtifactBackend")
        self._fs, _, parts = fsspec.get_fs_token_paths(base_url)  # type: ignore[attr-defined]
        self._base_url = base_url.rstrip("/")
        cache = cache_dir or os.getenv("QMTL_FEATURE_STORE_CACHE_DIR")
        super().__init__(cache)

    def _path(self, key: FeatureArtifactKey, version: int) -> Path:
        # Use local cache directory for atomic writes, then copy to remote
        return super()._path(key, version)

    def write(self, artifact: FeatureArtifact) -> FeatureArtifact:
        local = super().write(artifact)
        rel = local.key  # FeatureArtifactKey
        path = super()._path(rel, artifact.version)
        remote = f"{self._base_url}/{path.relative_to(self._base)}"
        with self._fs.open(remote, "wb") as fh:  # type: ignore[attr-defined]
            fh.write(path.read_bytes())
        return local

    def read(self, key: FeatureArtifactKey, version: int) -> FeatureArtifact | None:
        path = super()._path(key, version)
        remote = f"{self._base_url}/{path.relative_to(self._base)}"
        if not path.exists():
            try:
                with self._fs.open(remote, "rb") as fh:  # type: ignore[attr-defined]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("wb") as out:
                        out.write(fh.read())
            except FileNotFoundError:
                return None
        return super().read(key, version)


class RocksDbArtifactBackend:
    """Placeholder backend for RocksDB deployments."""

    def __init__(self, *_, **__):  # pragma: no cover - dependency placeholder
        raise RuntimeError("python-rocksdb must be installed to use RocksDbArtifactBackend")


BACKENDS: dict[str, type[FeatureArtifactBackend]] = {
    "local": LocalFileArtifactBackend,
    "object": ObjectStoreArtifactBackend,
    "rocksdb": RocksDbArtifactBackend,
}


def get_backend(name: str) -> type[FeatureArtifactBackend]:
    try:
        return BACKENDS[name]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"unknown feature artifact backend: {name!r}") from exc


__all__ = [
    "FeatureArtifactBackend",
    "LocalFileArtifactBackend",
    "ObjectStoreArtifactBackend",
    "RocksDbArtifactBackend",
    "get_backend",
]

