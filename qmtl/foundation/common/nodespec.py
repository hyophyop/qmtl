"""Utilities for canonical Node specification serialization."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .tagquery import (
    canonical_tag_query_params,
    canonical_tag_query_params_from_node,
)

# NOTE: Architecture spec (§3) requires NodeID inputs to exclude non-deterministic
# fields such as timestamps, random seeds, and environment payloads to preserve
# global stability across worlds/domains.
_PARAM_EXCLUDE_KEYS = {
    "world",
    "world_id",
    "world_ids",
    "execution_world",
    "execution_domain",
    "domain",
    "domains",
    "as_of",
    "partition",
    "dataset_fingerprint",
    "timestamp",
    "seed",
    "random_state",
    "env",
}

_PARAM_EXCLUDE_PREFIXES = ("env_",)


def _safe_deepcopy(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return value


def _normalize_dependencies(deps: Iterable[Any] | None) -> tuple[str, ...]:
    """Return a sorted tuple of dependency identifiers."""

    if not deps:
        return ()
    normalized: list[str] = []
    for dep in deps:
        if isinstance(dep, str):
            value = dep
        elif dep is None:
            continue
        else:
            value = str(dep)
        if value:
            normalized.append(value)
    return tuple(sorted(normalized))


def _sorted_deps(node: Mapping[str, Any]) -> list[str]:
    deps = node.get("inputs") or node.get("dependencies") or []
    return list(_normalize_dependencies(deps))


def _canonicalize_params(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _canonicalize_mapping(value)
    if isinstance(value, set):
        return _canonicalize_set(value)
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_canonicalize_params(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return value


def _canonicalize_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    canonical_items: list[tuple[str, Any]] = []
    for raw_key, raw_value in mapping.items():
        key_name = str(raw_key)
        lowered = key_name.lower()
        if _is_excluded_param_key(lowered):
            continue
        canonical_items.append((key_name, _canonicalize_params(raw_value)))
    # Sort using the normalized string form to guarantee deterministic output
    # even when heterogeneous key types are supplied (e.g., integers mixed with
    # strings). ``json.dumps(..., sort_keys=True)`` will take care of the final
    # ordering, but normalising here prevents ``TypeError`` from unsortable key
    # combinations before reaching the serializer.
    canonical: dict[str, Any] = {}
    for key_name, normalized_value in sorted(
        canonical_items, key=lambda item: item[0]
    ):
        canonical[key_name] = normalized_value
    return canonical


def _is_excluded_param_key(lowered_key: str) -> bool:
    if lowered_key in _PARAM_EXCLUDE_KEYS:
        return True
    return any(
        lowered_key.startswith(prefix) for prefix in _PARAM_EXCLUDE_PREFIXES
    )


def _canonicalize_set(values: set[Any]) -> list[Any]:
    items = [_canonicalize_params(item) for item in values]

    def _sort_key(x: Any) -> str:
        try:
            return json.dumps(
                x, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
        except Exception:
            return str(x)

    return sorted(items, key=_sort_key)


def _params_source_from_node(node: Mapping[str, Any]) -> Any:
    params_source = node.get("params")
    if params_source is None:
        params_source = node.get("config")
    return params_source


def _canonical_params_blob_from_value(params_source: Any) -> str:
    canonical = _canonicalize_params(params_source)
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_params_blob(node: Mapping[str, Any]) -> str:
    params_source = _params_source_from_node(node)
    if str(node.get("node_type", "")) == "TagQueryNode":
        params_source = canonical_tag_query_params_from_node(node)
    return _canonical_params_blob_from_value(params_source)


class CanonicalNodeSpec:
    """Builder object that owns canonical node serialization."""

    __slots__ = (
        "_node_type",
        "_interval",
        "_period",
        "_interval_payload",
        "_interval_payload_is_set",
        "_period_payload",
        "_period_payload_is_set",
        "_params_value",
        "_params_field",
        "_params_field_present",
        "_dependencies",
        "_schema_compat_id",
        "_code_hash",
        "_extras",
    )

    _RESERVED_EXTRA_KEYS = {
        "node_type",
        "interval",
        "period",
        "params",
        "config",
        "dependencies",
        "schema_compat_id",
        "code_hash",
    }

    def __init__(self) -> None:
        self._node_type: str = ""
        self._interval: int = 0
        self._period: int = 0
        self._interval_payload: Any = None
        self._interval_payload_is_set: bool = False
        self._period_payload: Any = None
        self._period_payload_is_set: bool = False
        self._params_value: Any = {}
        self._params_field: str = "params"
        self._params_field_present: bool = True
        self._dependencies: tuple[str, ...] = ()
        self._schema_compat_id: str = ""
        self._code_hash: str = ""
        self._extras: dict[str, Any] = {}

    # --- fluent setters -------------------------------------------------
    def with_node_type(self, value: Any) -> "CanonicalNodeSpec":
        self._node_type = str(value or "")
        return self

    def with_interval(
        self, value: Any, *, present: bool = True
    ) -> "CanonicalNodeSpec":
        self._interval = int(value or 0)
        self._interval_payload = value
        self._interval_payload_is_set = present
        return self

    def with_period(
        self, value: Any, *, present: bool = True
    ) -> "CanonicalNodeSpec":
        self._period = int(value or 0)
        self._period_payload = value
        self._period_payload_is_set = present
        return self

    def with_params(
        self, value: Any | None, *, field: str | None = None, present: bool = True
    ) -> "CanonicalNodeSpec":
        if field:
            self._params_field = str(field)
        elif field is None:
            self._params_field = "params"
        self._params_value = _safe_deepcopy(value)
        self._params_field_present = present
        return self

    def with_config(self, value: Any | None) -> "CanonicalNodeSpec":
        return self.with_params(value, field="config")

    def with_dependencies(self, deps: Iterable[Any] | None) -> "CanonicalNodeSpec":
        self._dependencies = _normalize_dependencies(deps)
        return self

    def with_schema_compat_id(
        self, value: Any | None, *, fallback: Any | None = None
    ) -> "CanonicalNodeSpec":
        compat = str(value or "").strip()
        if not compat and fallback is not None:
            compat = str(fallback or "").strip()
        self._schema_compat_id = compat
        return self

    def with_code_hash(self, value: Any | None) -> "CanonicalNodeSpec":
        self._code_hash = str(value or "")
        return self

    def with_extra(self, key: str, value: Any) -> "CanonicalNodeSpec":
        if key in self._RESERVED_EXTRA_KEYS:
            raise ValueError(f"{key!r} is reserved for canonical serialization")
        self._extras[key] = value
        return self

    def update_extras(self, data: Mapping[str, Any]) -> "CanonicalNodeSpec":
        for key, value in data.items():
            if key in self._RESERVED_EXTRA_KEYS:
                continue
            self._extras[key] = value
        return self

    # --- canonical accessors -------------------------------------------
    @property
    def node_type(self) -> str:
        return self._node_type

    @property
    def interval(self) -> int:
        return self._interval

    @property
    def period(self) -> int:
        return self._period

    @property
    def dependencies(self) -> tuple[str, ...]:
        return self._dependencies

    @property
    def schema_compat_id(self) -> str:
        return self._schema_compat_id

    @property
    def code_hash(self) -> str:
        return self._code_hash

    @property
    def params_field(self) -> str:
        return self._params_field

    @property
    def params_source(self) -> Any:
        return self._params_value

    @property
    def extras(self) -> Mapping[str, Any]:
        return self._extras

    def to_payload(self) -> dict[str, Any]:
        params_field = self._params_field or "params"
        interval_value = (
            self._interval_payload
            if self._interval_payload_is_set
            else self._interval
        )
        period_value = (
            self._period_payload
            if self._period_payload_is_set
            else self._period
        )
        payload: dict[str, Any] = {
            "node_type": self._node_type,
            "interval": interval_value,
            "period": period_value,
            "dependencies": list(self._dependencies),
            "schema_compat_id": self._schema_compat_id,
            "code_hash": self._code_hash,
        }
        if self._params_field_present:
            payload[params_field] = _safe_deepcopy(self._params_value)
        for key, value in self._extras.items():
            payload[key] = value
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "CanonicalNodeSpec":
        spec = cls()
        params_field = "params"
        if "params" in payload:
            params_field = "params"
        elif "config" in payload:
            params_field = "config"
        params_value = payload.get(params_field)
        deps_value = payload.get("dependencies")
        if deps_value is None:
            deps_value = payload.get("inputs")
        spec.with_node_type(payload.get("node_type"))
        spec.with_interval(
            payload.get("interval"), present="interval" in payload
        )
        spec.with_period(payload.get("period"), present="period" in payload)
        spec.with_params(
            params_value, field=params_field, present=params_field in payload
        )
        spec.with_dependencies(deps_value)
        spec.with_schema_compat_id(
            payload.get("schema_compat_id"), fallback=payload.get("schema_id")
        )
        spec.with_code_hash(payload.get("code_hash"))

        reserved = set(cls._RESERVED_EXTRA_KEYS)
        reserved.add(params_field)
        extras: dict[str, Any] = {}
        for key, value in payload.items():
            if key in reserved:
                continue
            extras[key] = value
        if extras:
            spec.update_extras(extras)
        return spec


def serialize_nodespec(node: Mapping[str, Any] | CanonicalNodeSpec) -> bytes:
    if isinstance(node, CanonicalNodeSpec):
        node_type = node.node_type
        interval = node.interval
        period = node.period
        deps = list(node.dependencies)
        schema_compat_id = node.schema_compat_id
        code_hash = node.code_hash
        params_source = node.params_source
        if node_type == "TagQueryNode":
            tags_source = None
            match_mode_source = None
            extras = node.extras
            if isinstance(params_source, Mapping):
                tags_source = params_source.get("query_tags") or params_source.get("tags")
                match_mode_source = params_source.get("match_mode")
            if tags_source is None:
                tags_source = extras.get("tags") if extras else None
            if match_mode_source is None:
                match_mode_source = extras.get("match_mode") if extras else None
            params_source = canonical_tag_query_params(
                tags_source if tags_source is not None else params_source,
                interval=interval,
                match_mode=match_mode_source,
            )
        params_blob = _canonical_params_blob_from_value(params_source)
    else:
        node_type = str(node.get("node_type", ""))
        interval = int(node.get("interval") or 0)
        period = int(node.get("period") or 0)
        deps = _sorted_deps(node)
        schema_compat_id = str(node.get("schema_compat_id", ""))
        if not schema_compat_id:
            schema_compat_id = str(node.get("schema_id", ""))
        code_hash = str(node.get("code_hash", ""))
        params_blob = _canonical_params_blob(node)
    payload = "|".join(
        [
            node_type,
            str(interval),
            str(period),
            params_blob,
            ",".join(deps),
            schema_compat_id,
            code_hash,
        ]
    )
    return payload.encode()


__all__ = ["serialize_nodespec", "CanonicalNodeSpec"]
