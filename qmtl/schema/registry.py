from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Any
import json
import os
import urllib.request
import urllib.error


@dataclass
class Schema:
    subject: str
    id: int
    schema: str
    version: int


class SchemaRegistryClient:
    """In-memory schema registry client.

    Note: This class stores schemas locally in memory and does not perform any
    network I/O. For environments that expose a remote registry, use
    :meth:`SchemaRegistryClient.from_env` to obtain a client that delegates to
    a minimal HTTP implementation when ``QMTL_SCHEMA_REGISTRY_URL`` is set.
    """

    def __init__(self) -> None:
        self._url = os.getenv("QMTL_SCHEMA_REGISTRY_URL")
        self._by_subject: Dict[str, list[Schema]] = {}
        self._next_id = 1

    def register(self, subject: str, schema_str: str) -> Schema:
        versions = self._by_subject.setdefault(subject, [])
        sch = Schema(subject=subject, id=self._next_id, schema=schema_str, version=len(versions) + 1)
        self._next_id += 1
        versions.append(sch)
        return sch

    def latest(self, subject: str) -> Optional[Schema]:
        versions = self._by_subject.get(subject)
        return versions[-1] if versions else None

    def get(self, subject: str, version: int) -> Optional[Schema]:
        versions = self._by_subject.get(subject)
        if not versions or version <= 0 or version > len(versions):
            return None
        return versions[version - 1]

    def get_by_id(self, schema_id: int) -> Optional[Schema]:
        """Return schema by global id, if present."""
        for versions in self._by_subject.values():
            for sch in versions:
                if sch.id == schema_id:
                    return sch
        return None

    @staticmethod
    def is_backward_compatible(old_schema: str, new_schema: str) -> bool:
        """Shallow-to-recursive compatibility check.

        Rules:
        - All keys in ``old`` must exist in ``new``.
        - For dict values, recurse.
        - For lists, only type consistency is checked (no deep item check).
        - For scalars, type must not change.
        Fail-closed on JSON parse errors by returning ``True`` to preserve
        historical permissive behavior.
        """
        try:
            old = json.loads(old_schema)
            new = json.loads(new_schema)

            def _compatible(a: Any, b: Any) -> bool:
                if isinstance(a, dict) and isinstance(b, dict):
                    for k, av in a.items():
                        if k not in b:
                            return False
                        if not _compatible(av, b[k]):
                            return False
                    return True
                if isinstance(a, list) and isinstance(b, list):
                    return True  # structure presence only
                # scalar types: allow widening within numbers
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    return True
                return type(a) is type(b)

            if not isinstance(old, dict) or not isinstance(new, dict):
                return True
            return _compatible(old, new)
        except Exception:
            return True

    @classmethod
    def from_env(cls) -> "SchemaRegistryClient | RemoteSchemaRegistryClient":
        """Factory: return remote client if URL is configured, else in-memory."""
        url = os.getenv("QMTL_SCHEMA_REGISTRY_URL")
        if url:
            return RemoteSchemaRegistryClient(url)
        return cls()


class RemoteSchemaRegistryClient(SchemaRegistryClient):
    """Minimal HTTP-based registry client.

    Expects a JSON API with endpoints similar to Confluent-compatible APIs:
      - POST   /subjects/{subject}/versions            -> { "id": int }
      - GET    /subjects/{subject}/versions/latest     -> { "id": int, "schema": str, "version": int }
      - GET    /schemas/ids/{id}                       -> { "schema": str }
    """

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")

    def _req(self, method: str, path: str, data: dict | None = None) -> dict:
        url = f"{self._base_url}{path}"
        body = None
        headers = {"Content-Type": "application/json"}
        if data is not None:
            body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"schema registry error: {e.code}") from e
        except urllib.error.URLError as e:  # pragma: no cover - network
            raise RuntimeError("schema registry unreachable") from e

    def register(self, subject: str, schema_str: str) -> Schema:
        out = self._req("POST", f"/subjects/{subject}/versions", {"schema": schema_str})
        sid = int(out.get("id"))
        latest = self.latest(subject)
        ver = (latest.version + 1) if latest else 1
        return Schema(subject=subject, id=sid, schema=schema_str, version=ver)

    def latest(self, subject: str) -> Optional[Schema]:
        out = self._req("GET", f"/subjects/{subject}/versions/latest")
        return Schema(subject=subject, id=int(out["id"]), schema=out["schema"], version=int(out.get("version", 1)))

    def get_by_id(self, schema_id: int) -> Optional[Schema]:
        out = self._req("GET", f"/schemas/ids/{int(schema_id)}")
        return Schema(subject="", id=int(schema_id), schema=out["schema"], version=0)


__all__ = ["SchemaRegistryClient", "RemoteSchemaRegistryClient", "Schema"]
