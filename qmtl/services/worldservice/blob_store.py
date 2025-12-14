"""Blob store abstractions for large payloads (covariance/returns refs)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

import asyncio


class BlobStore(Protocol):
    def write(self, name: str, payload: Mapping[str, Any]) -> str:  # pragma: no cover - interface
        ...

    def read(self, ref: str) -> dict[str, Any]:  # pragma: no cover - interface
        ...


class JsonBlobStore:
    """File-backed blob store for large payloads (e.g., covariance matrices)."""

    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, payload: Mapping[str, Any]) -> str:
        path = self._base / f"{name}.json"
        path.write_text(json.dumps(payload, sort_keys=True))
        return f"file://{path}"

    def read(self, ref: str) -> dict[str, Any]:
        if ref.startswith("file://"):
            path = Path(ref[len("file://") :])
        else:
            path = Path(ref)
        return json.loads(path.read_text())


class RedisBlobStore:
    """Redis-backed blob store (string JSON)."""

    def __init__(self, client, *, prefix: str = "risk-blobs:", ttl: int | None = None) -> None:
        self._client = client
        self._prefix = prefix
        self._ttl = ttl

    def write(self, name: str, payload: Mapping[str, Any]) -> str:
        key = f"{self._prefix}{name}"
        data = json.dumps(payload, sort_keys=True)
        setter = getattr(self._client, "set", None)
        if setter is None:
            raise RuntimeError("Redis client missing set method")
        if asyncio.iscoroutinefunction(setter):
            raise RuntimeError("RedisBlobStore expects a sync client; async client not supported here")
        setter(key, data)
        if self._ttl:
            expire = getattr(self._client, "expire", None)
            if expire:
                expire(key, int(self._ttl))
        return f"redis://{key}"

    def read(self, ref: str) -> dict[str, Any]:
        key = ref[len("redis://") :] if ref.startswith("redis://") else ref
        getter = getattr(self._client, "get", None)
        if getter is None:
            raise RuntimeError("Redis client missing get method")
        if asyncio.iscoroutinefunction(getter):
            raise RuntimeError("RedisBlobStore expects a sync client; async client not supported here")
        data = getter(key)
        if not data:
            raise FileNotFoundError(ref)
        if isinstance(data, bytes):
            data = data.decode()
        return json.loads(data)


class S3BlobStore:
    """S3-backed blob store (optional dependency)."""

    def __init__(self, bucket: str, *, prefix: str = "", client=None) -> None:
        self._bucket = bucket
        self._prefix = prefix.rstrip("/")
        self._client = client

    def write(self, name: str, payload: Mapping[str, Any]) -> str:
        client = self._client or _lazy_boto3()
        if client is None:
            raise RuntimeError("boto3 not available for S3 blob store")
        key = "/".join(filter(None, [self._prefix, f"{name}.json"]))
        body = json.dumps(payload, sort_keys=True).encode()
        client.put_object(Bucket=self._bucket, Key=key, Body=body)
        return f"s3://{self._bucket}/{key}"

    def read(self, ref: str) -> dict[str, Any]:
        client = self._client or _lazy_boto3()
        if client is None:
            raise RuntimeError("boto3 not available for S3 blob store")
        bucket, key = _split_s3_ref(ref)
        obj = client.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        if isinstance(body, bytes):
            body = body.decode()
        return json.loads(body)


def _split_s3_ref(ref: str) -> tuple[str, str]:
    text = ref[len("s3://") :] if ref.startswith("s3://") else ref
    if "/" not in text:
        raise ValueError("invalid s3 ref")
    bucket, key = text.split("/", 1)
    return bucket, key


def _lazy_boto3():
    try:  # pragma: no cover - optional dep
        import boto3
    except Exception:
        return None
    return boto3.client("s3")


def build_blob_store(
    *,
    store_type: str = "file",
    base_dir: str | os.PathLike[str] | None = None,
    bucket: str | None = None,
    prefix: str | None = None,
    redis_client=None,
    redis_dsn: str | None = None,
    redis_prefix: str | None = None,
    cache_ttl: int | None = None,
) -> BlobStore:
    """Factory for risk-hub blob stores following dev/prod templates."""

    normalized_type = (store_type or "file").lower()
    if normalized_type == "file":
        target_dir = base_dir or ".risk_blobs"
        return JsonBlobStore(target_dir)

    if normalized_type == "redis":
        client = redis_client
        if client is None and redis_dsn:
            try:  # pragma: no cover - exercised indirectly
                import redis as redis_sync
            except Exception as exc:  # pragma: no cover - optional dependency path
                raise RuntimeError("Redis client unavailable for redis blob store") from exc
            client = redis_sync.from_url(redis_dsn, decode_responses=True)
        if client is None:
            raise ValueError("redis blob store requires redis_client or redis_dsn")
        ttl_final = cache_ttl if cache_ttl is not None else 900
        return RedisBlobStore(client, prefix=redis_prefix or "risk-blobs:", ttl=ttl_final)

    if normalized_type == "s3":
        if not bucket:
            raise ValueError("s3 blob store requires bucket")
        return S3BlobStore(bucket=bucket, prefix=prefix or "")

    raise ValueError(f"Unsupported blob store type: {store_type}")


__all__ = ["BlobStore", "JsonBlobStore", "RedisBlobStore", "S3BlobStore", "build_blob_store"]
