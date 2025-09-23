from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qmtl.sdk.util import parse_interval


def _extract_schema_compat_id(schema: Any, expected_schema: Any) -> str | None:
    """Extract a schema compatibility identifier from provided schemas."""

    compat_id: Any = None
    if isinstance(schema, dict):
        compat_id = (
            schema.get("schema_compat_id")
            or schema.get("compat_id")
            or schema.get("compatId")
        )
    if compat_id is None and isinstance(expected_schema, dict):
        compat_id = (
            expected_schema.get("schema_compat_id")
            or expected_schema.get("compat_id")
            or expected_schema.get("compatId")
        )
    if compat_id is None:
        return None
    return str(compat_id)


@dataclass(frozen=True)
class NodeConfig:
    """Validated configuration payload used to initialize :class:`Node`."""

    name: str | None
    tags: list[str]
    interval: int | None
    period: int | None
    config: dict[str, Any]
    schema: dict[str, Any]
    expected_schema: dict[str, Any]
    inputs: list[Any]
    schema_compat_id: str
    allowed_lateness: int
    on_late: str
    runtime_compat: str
    enable_feature_artifacts: bool

    @classmethod
    def build(
        cls,
        *,
        input: Any,
        compute_fn: Any,
        name: str | None,
        tags: list[str] | None,
        interval: int | str | None,
        period: int | None,
        config: dict | None,
        schema: dict | None,
        expected_schema: dict | None,
        allowed_lateness: int,
        on_late: str,
        runtime_compat: str,
        validator,
        hash_utils,
    ) -> "NodeConfig":
        if isinstance(interval, str):
            interval = parse_interval(interval)

        validator.validate_compute_fn(compute_fn)
        (
            validated_name,
            validated_tags,
            interval_val,
            period_val,
        ) = validator.validate_node_params(
            name,
            tags,
            interval,
            period,
            config,
            schema,
            expected_schema,
        )

        if isinstance(interval_val, str):
            interval_val = parse_interval(interval_val)

        normalized_inputs = validator.normalize_inputs(input)
        config = config or {}
        schema = schema or {}
        expected_schema = expected_schema or {}
        enable_feature_artifacts = bool(
            config.get("enable_feature_artifacts", False)
        )
        schema_compat_id = _extract_schema_compat_id(schema, expected_schema) or hash_utils.schema_hash(
            schema
        )

        return cls(
            name=validated_name,
            tags=validated_tags,
            interval=interval_val,
            period=period_val,
            config=config,
            schema=schema,
            expected_schema=expected_schema,
            inputs=normalized_inputs,
            schema_compat_id=schema_compat_id,
            allowed_lateness=int(allowed_lateness),
            on_late=on_late,
            runtime_compat=runtime_compat,
            enable_feature_artifacts=enable_feature_artifacts,
        )


__all__ = ["NodeConfig", "_extract_schema_compat_id"]

