from __future__ import annotations

import inspect
from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from typing import Any, List

from qmtl.foundation.validation_core import Rule, RuleSet, ValidationResult
from .util import parse_interval, parse_period, validate_tag, validate_name
from .exceptions import InvalidParameterError

__all__ = [
    "normalize_inputs",
    "validate_node_params",
    "validate_compute_fn",
    "validate_feed_params",
    "validate_tag",
    "validate_name",
]


@dataclass(slots=True)
class _NodeParamsContext:
    """Context object used by validation rules for node parameters."""

    name: str | None
    tags: list[str] | None
    interval: int | str | None
    period: int | None
    config: dict | None
    schema: dict | None
    expected_schema: dict | None
    validated_name: str | None = None
    validated_tags: list[str] | None = None
    interval_val: int | None = None
    period_val: int | None = None


class _NameIntervalPeriodRule(Rule[_NodeParamsContext]):
    code = "NODE_NAME_INTERVAL_PERIOD"
    description = "Validate node name, interval and period relationship."

    def validate(self, context: _NodeParamsContext) -> ValidationResult:
        interval_val = (
            parse_interval(context.interval) if context.interval is not None else None
        )
        period_val = (
            parse_period(context.period) if context.period is not None else None
        )

        if interval_val is not None and period_val is not None and period_val < 1:
            raise InvalidParameterError(
                "period must be at least 1 when interval is specified"
            )

        validated_name = validate_name(context.name)

        context.interval_val = interval_val
        context.period_val = period_val
        context.validated_name = validated_name

        return ValidationResult.success()


class _TagsRule(Rule[_NodeParamsContext]):
    code = "NODE_TAGS"
    description = "Validate node tags collection and individual tag values."

    def validate(self, context: _NodeParamsContext) -> ValidationResult:
        tags = context.tags
        validated_tags: List[str] = []

        if tags is None:
            context.validated_tags = validated_tags
            return ValidationResult.success()

        if not isinstance(tags, list):
            raise InvalidParameterError("tags must be a list")

        seen_tags: set[str] = set()
        for tag in tags:
            validated_tag = validate_tag(tag)
            if validated_tag in seen_tags:
                raise InvalidParameterError(f"duplicate tag: {validated_tag!r}")
            seen_tags.add(validated_tag)
            validated_tags.append(validated_tag)

        context.validated_tags = validated_tags
        return ValidationResult.success()


class _MappingParamsRule(Rule[_NodeParamsContext]):
    code = "NODE_MAPPING_PARAMS"
    description = "Validate mapping-type node parameters such as config and schema."

    def validate(self, context: _NodeParamsContext) -> ValidationResult:
        if context.config is not None and not isinstance(context.config, dict):
            raise InvalidParameterError("config must be a dictionary")
        if context.schema is not None and not isinstance(context.schema, dict):
            raise InvalidParameterError("schema must be a dictionary")
        if context.expected_schema is not None and not isinstance(
            context.expected_schema, dict
        ):
            raise InvalidParameterError("expected_schema must be a dictionary")
        return ValidationResult.success()


def normalize_inputs(inp: Any) -> list:
    """Normalize ``inp`` into a list of upstream nodes."""
    from .node import Node  # local import to avoid circular dependency

    if inp is None:
        return []
    if isinstance(inp, Node):
        return [inp]
    if isinstance(inp, Mapping):
        raise TypeError("mapping inputs no longer supported")
    if isinstance(inp, Iterable):
        return list(inp)
    raise TypeError("invalid input type")


def validate_node_params(
    name: str | None,
    tags: list[str] | None,
    interval: int | str | None,
    period: int | None,
    config: dict | None,
    schema: dict | None,
    expected_schema: dict | None,
) -> tuple[str | None, list[str], int | None, int | None]:
    """Validate common ``Node`` constructor arguments."""
    context = _NodeParamsContext(
        name=name,
        tags=tags,
        interval=interval,
        period=period,
        config=config,
        schema=schema,
        expected_schema=expected_schema,
    )

    rules: tuple[Rule[_NodeParamsContext], ...] = (
        _NameIntervalPeriodRule(),
        _TagsRule(),
        _MappingParamsRule(),
    )
    RuleSet(rules=rules).validate(context)

    validated_tags = context.validated_tags or []
    return context.validated_name, validated_tags, context.interval_val, context.period_val


def validate_compute_fn(compute_fn) -> None:
    """Ensure ``compute_fn`` has a valid callable signature."""
    if compute_fn is None:
        return
    sig = inspect.signature(compute_fn)
    positional = [
        p
        for p in sig.parameters.values()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    has_var_positional = any(
        p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
    )
    if len(positional) != 1 or has_var_positional:
        raise TypeError(
            "compute_fn must accept exactly one positional argument (지원되지 않는 함수 시그니처). compute_fn(view) 형태로 작성했는지 확인하세요"
        )


def validate_feed_params(
    upstream_id: str,
    interval: int,
    timestamp: int,
    on_missing: str,
) -> None:
    """Validate parameters for :meth:`Node.feed`.

    Centralizes type/range checking so error messages and exception types remain
    consistent across the SDK.
    """
    if not isinstance(upstream_id, str):
        raise InvalidParameterError("upstream_id must be a string")
    if not upstream_id.strip():
        raise InvalidParameterError("upstream_id must not be empty")

    if not isinstance(interval, int):
        raise InvalidParameterError("interval must be an integer")
    if interval <= 0:
        raise InvalidParameterError("interval must be positive")

    if not isinstance(timestamp, int):
        raise InvalidParameterError("timestamp must be an integer")
    if timestamp < 0:
        raise InvalidParameterError("timestamp must not be negative")

    if on_missing not in ("skip", "fail"):
        raise InvalidParameterError("on_missing must be 'skip' or 'fail'")
