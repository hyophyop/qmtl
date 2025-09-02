from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import json
import os


@dataclass
class Schema:
    subject: str
    id: int
    schema: str
    version: int


class SchemaRegistryClient:
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

    @staticmethod
    def is_backward_compatible(old_schema: str, new_schema: str) -> bool:
        try:
            old = json.loads(old_schema)
            new = json.loads(new_schema)
            if not isinstance(old, dict) or not isinstance(new, dict):
                return True
            return set(old.keys()).issubset(set(new.keys()))
        except Exception:
            return True


__all__ = ["SchemaRegistryClient", "Schema"]
