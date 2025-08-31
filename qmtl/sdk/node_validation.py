from __future__ import annotations

"""Validation helpers for :mod:`qmtl.sdk.node`."""

from collections.abc import Iterable, Mapping

from .exceptions import InvalidParameterError
from .util import validate_tag, validate_name


def normalize_inputs(inp: "Node | Iterable[Node] | None") -> list["Node"]:
    """Normalize ``inp`` into a list of nodes.

    Raises
    ------
    TypeError
        If ``inp`` is neither ``None``, a ``Node`` instance nor an iterable of
        ``Node`` objects.
    """
    if inp is None:
        return []
    from .node import Node as NodeType  # local import to avoid circular
    if isinstance(inp, NodeType):
        return [inp]
    if isinstance(inp, Mapping):
        raise TypeError("mapping inputs no longer supported")
    if isinstance(inp, Iterable):
        return list(inp)
    raise TypeError("invalid input type")


def validate_tags(tags: list[str] | None) -> list[str]:
    """Return a validated copy of ``tags``.

    Duplicate tags raise :class:`InvalidParameterError`.
    """
    validated: list[str] = []
    if tags is None:
        return validated
    if not isinstance(tags, list):
        raise InvalidParameterError("tags must be a list")
    seen: set[str] = set()
    for tag in tags:
        validated_tag = validate_tag(tag)
        if validated_tag in seen:
            raise InvalidParameterError(f"duplicate tag: {validated_tag!r}")
        seen.add(validated_tag)
        validated.append(validated_tag)
    return validated


def validate_name_value(name: str | None) -> str | None:
    """Validate ``name`` and return the normalized value."""
    return validate_name(name)


def validate_config_schema(config, schema) -> None:
    """Validate optional ``config`` and ``schema`` dictionaries."""
    if config is not None and not isinstance(config, dict):
        raise InvalidParameterError("config must be a dictionary")
    if schema is not None and not isinstance(schema, dict):
        raise InvalidParameterError("schema must be a dictionary")
