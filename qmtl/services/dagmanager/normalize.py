"""Normalization helpers for DAG diff inputs."""

from __future__ import annotations


__all__ = [
    "normalize_version",
    "normalize_execution_domain",
    "stringify",
]


def stringify(value: object) -> str:
    """Convert ``value`` to a trimmed string.

    ``None`` maps to an empty string to simplify downstream defaulting logic
    while numeric values preserve their canonical textual representation.
    """

    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def normalize_version(raw: object, default: str = "v1") -> str:
    """Normalize version identifiers used for queue topic suffixes."""

    if isinstance(raw, (int, float)):
        value = str(raw)
    elif isinstance(raw, str):
        value = raw.strip()
    else:
        value = ""
    if not value:
        return default
    cleaned = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_", "."}:
            cleaned.append(ch)
        else:
            cleaned.append("-")
    result = "".join(cleaned).strip("-_.")
    return result or default


def normalize_execution_domain(raw: object) -> str:
    """Lowercase the execution domain or fall back to ``"live"``."""

    value = stringify(raw)
    return value.lower() or "live"
