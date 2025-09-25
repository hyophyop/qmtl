from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Optional
import json
import logging
import os
import urllib.request
import urllib.error

from qmtl.foundation.common.metrics_factory import get_or_create_counter


logger = logging.getLogger(__name__)


class SchemaValidationMode(Enum):
    """Supported validation modes for schema governance."""

    CANARY = "canary"
    STRICT = "strict"

    @classmethod
    def parse(cls, value: str | "SchemaValidationMode" | None) -> "SchemaValidationMode":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.CANARY
        normalized = str(value).strip().lower()
        for mode in cls:
            if mode.value == normalized:
                return mode
        raise ValueError(f"Unsupported schema validation mode: {value!r}")


@dataclass
class SchemaValidationReport:
    """Outcome of a schema compatibility check."""

    subject: str
    mode: SchemaValidationMode
    compatible: bool
    previous_version: int | None
    breaking_changes: list[str]
    added_fields: list[str]
    schema_id: int | None = None
    registered_version: int | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a serializable representation of the report."""

        return {
            "subject": self.subject,
            "mode": self.mode.value,
            "compatible": self.compatible,
            "previous_version": self.previous_version,
            "breaking_changes": list(self.breaking_changes),
            "added_fields": list(self.added_fields),
            "schema_id": self.schema_id,
            "registered_version": self.registered_version,
        }


class SchemaValidationError(RuntimeError):
    """Raised when validation fails in strict mode."""


class SchemaRegistryError(RuntimeError):
    """Raised for transport-level registry failures."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


_VALIDATION_FAILURES = get_or_create_counter(
    "seamless_schema_validation_failures_total",
    "Total number of schema validation failures detected by the registry governance layer.",
    labelnames=("subject", "mode"),
    test_value_attr="_value",
)


@dataclass
class Schema:
    subject: str
    id: int
    schema: str
    version: int


class SchemaRegistryClient:
    """In-memory schema registry client with governance hooks."""

    def __init__(self, *, validation_mode: SchemaValidationMode | str | None = None) -> None:
        self._url = os.getenv("QMTL_SCHEMA_REGISTRY_URL")
        self._by_subject: Dict[str, list[Schema]] = {}
        self._next_id = 1
        env_mode = os.getenv("QMTL_SCHEMA_VALIDATION_MODE")
        self._validation_mode = SchemaValidationMode.parse(validation_mode or env_mode)
        self._last_reports: Dict[str, SchemaValidationReport] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def validation_mode(self) -> SchemaValidationMode:
        return self._validation_mode

    def set_validation_mode(self, mode: SchemaValidationMode | str) -> None:
        self._validation_mode = SchemaValidationMode.parse(mode)

    def last_validation(self, subject: str) -> SchemaValidationReport | None:
        return self._last_reports.get(subject)

    def register(
        self,
        subject: str,
        schema_str: str,
        *,
        validation_mode: SchemaValidationMode | str | None = None,
    ) -> Schema:
        mode = SchemaValidationMode.parse(validation_mode or self._validation_mode)
        previous = self.latest(subject)
        report = self.validate(subject, schema_str, previous_schema=previous, mode=mode)
        if not report.compatible:
            _VALIDATION_FAILURES.labels(subject=subject, mode=mode.value).inc()
            logger.warning(
                "Schema validation failure for subject '%s' in %s mode: breaking=%s added=%s",
                subject,
                mode.value,
                report.breaking_changes,
                report.added_fields,
            )
            if mode is SchemaValidationMode.STRICT:
                self._last_reports[subject] = report
                raise SchemaValidationError(
                    f"Schema update rejected: incompatible with previous version {previous.version if previous else 'N/A'}"
                )
        schema = self._register_impl(subject, schema_str, previous)
        self._last_reports[subject] = replace(
            report,
            schema_id=schema.id,
            registered_version=schema.version,
        )
        return schema

    def validate(
        self,
        subject: str,
        schema_str: str,
        *,
        previous_schema: Schema | None = None,
        mode: SchemaValidationMode | str | None = None,
    ) -> SchemaValidationReport:
        mode_obj = SchemaValidationMode.parse(mode or self._validation_mode)
        previous = previous_schema or self.latest(subject)
        breaking_changes: list[str] = []
        added_fields: list[str] = []

        if previous is None:
            compatible = True
        else:
            prev_paths = _flatten_schema(previous.schema)
            new_paths = _flatten_schema(schema_str)
            prev_keys = set(prev_paths)
            new_keys = set(new_paths)
            missing = sorted(prev_keys - new_keys)
            breaking_changes.extend(missing)
            changed = sorted(path for path in (prev_keys & new_keys) if prev_paths[path] != new_paths[path])
            breaking_changes.extend(changed)
            added_fields.extend(sorted(new_keys - prev_keys))
            compatible = not breaking_changes

        report = SchemaValidationReport(
            subject=subject,
            mode=mode_obj,
            compatible=compatible,
            previous_version=previous.version if previous else None,
            breaking_changes=breaking_changes,
            added_fields=added_fields,
        )
        return report

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_impl(self, subject: str, schema_str: str, previous: Schema | None) -> Schema:
        versions = self._by_subject.setdefault(subject, [])
        sch = Schema(subject=subject, id=self._next_id, schema=schema_str, version=len(versions) + 1)
        self._next_id += 1
        versions.append(sch)
        return sch

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
            raise SchemaRegistryError(f"schema registry error: {e.code}", status_code=e.code) from e
        except urllib.error.URLError as e:  # pragma: no cover - network
            raise SchemaRegistryError("schema registry unreachable") from e

    def register(
        self,
        subject: str,
        schema_str: str,
        *,
        validation_mode: SchemaValidationMode | str | None = None,
    ) -> Schema:
        return super().register(subject, schema_str, validation_mode=validation_mode)

    def latest(self, subject: str) -> Optional[Schema]:
        try:
            out = self._req("GET", f"/subjects/{subject}/versions/latest")
        except SchemaRegistryError as exc:
            if exc.status_code == 404:
                return None
            raise
        return Schema(subject=subject, id=int(out["id"]), schema=out["schema"], version=int(out.get("version", 1)))

    def get_by_id(self, schema_id: int) -> Optional[Schema]:
        try:
            out = self._req("GET", f"/schemas/ids/{int(schema_id)}")
        except SchemaRegistryError as exc:
            if exc.status_code == 404:
                return None
            raise
        return Schema(subject="", id=int(schema_id), schema=out["schema"], version=0)

    def _register_impl(self, subject: str, schema_str: str, previous: Schema | None) -> Schema:
        out = self._req("POST", f"/subjects/{subject}/versions", {"schema": schema_str})
        sid = int(out.get("id"))
        try:
            latest = self.latest(subject)
        except SchemaRegistryError:
            latest = None
        if latest is not None:
            return latest
        version = (previous.version + 1) if previous else 1
        return Schema(subject=subject, id=sid, schema=schema_str, version=version)


def _flatten_schema(schema_str: str) -> Dict[str, str]:
    try:
        parsed = json.loads(schema_str)
    except json.JSONDecodeError:
        return {"<raw>": "text"}
    if isinstance(parsed, dict):
        return _flatten_dict(parsed)
    return {"<root>": type(parsed).__name__}


def _flatten_dict(value: dict, prefix: str = "") -> Dict[str, str]:
    flattened: Dict[str, str] = {}
    for key, inner in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(inner, dict):
            if inner:
                flattened.update(_flatten_dict(inner, path))
            else:
                flattened[path] = "object"
        elif isinstance(inner, list):
            flattened[path] = "list"
        else:
            flattened[path] = type(inner).__name__
    return flattened


__all__ = [
    "SchemaRegistryClient",
    "RemoteSchemaRegistryClient",
    "Schema",
    "SchemaValidationMode",
    "SchemaValidationReport",
    "SchemaValidationError",
    "SchemaRegistryError",
]
