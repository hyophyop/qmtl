"""Helpers for world/execution-domain scoped local storage paths."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from qmtl.foundation.common.compute_key import DEFAULT_EXECUTION_DOMAIN

from .configuration import get_connectors_config

EPHEMERAL_EXECUTION_DOMAINS = frozenset({"backtest", "dryrun"})


def _sanitize_scope_component(value: str | None, *, fallback: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return fallback
    normalized = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-.")
    return normalized or fallback


def resolve_runtime_scope(
    *,
    world_id: str | None = None,
    execution_domain: str | None = None,
) -> tuple[str, str]:
    """Return normalized world/domain scope used for local storage."""

    raw_world = world_id or os.getenv("WORLD_ID") or "default"
    raw_domain = execution_domain
    if raw_domain is None:
        try:
            raw_domain = get_connectors_config().execution_domain
        except Exception:  # pragma: no cover - defensive
            raw_domain = None
    raw_domain = raw_domain or os.getenv("QMTL_EXECUTION_DOMAIN") or DEFAULT_EXECUTION_DOMAIN
    return (
        _sanitize_scope_component(raw_world, fallback="default"),
        _sanitize_scope_component(raw_domain, fallback=DEFAULT_EXECUTION_DOMAIN),
    )


def _is_default_or_relative(raw_path: str | os.PathLike[str], default_path: str | None) -> bool:
    expanded = Path(raw_path).expanduser()
    if not expanded.is_absolute():
        return True
    if default_path is None:
        return False
    return expanded == Path(default_path).expanduser()


def scoped_directory_path(
    raw_path: str | os.PathLike[str],
    *,
    storage_kind: str,
    default_path: str | None = None,
    world_id: str | None = None,
    execution_domain: str | None = None,
) -> Path:
    """Return a directory path scoped for local writes when needed."""

    base = Path(raw_path).expanduser()
    scope_world, scope_domain = resolve_runtime_scope(
        world_id=world_id,
        execution_domain=execution_domain,
    )
    if scope_domain not in EPHEMERAL_EXECUTION_DOMAINS:
        return base
    root = base
    if _is_default_or_relative(raw_path, default_path):
        root = Path(tempfile.gettempdir()) / "qmtl" / storage_kind
    return root / f"world={scope_world}" / f"execution_domain={scope_domain}"


def scoped_file_path(
    raw_path: str | os.PathLike[str],
    *,
    storage_kind: str,
    default_path: str | None = None,
    world_id: str | None = None,
    execution_domain: str | None = None,
) -> Path:
    """Return a file path scoped for local writes when needed."""

    base = Path(raw_path).expanduser()
    scope_world, scope_domain = resolve_runtime_scope(
        world_id=world_id,
        execution_domain=execution_domain,
    )
    if scope_domain not in EPHEMERAL_EXECUTION_DOMAINS:
        return base
    root = base.parent
    if _is_default_or_relative(raw_path, default_path):
        root = Path(tempfile.gettempdir()) / "qmtl" / storage_kind
    return root / f"world={scope_world}" / f"execution_domain={scope_domain}" / base.name


__all__ = [
    "EPHEMERAL_EXECUTION_DOMAINS",
    "resolve_runtime_scope",
    "scoped_directory_path",
    "scoped_file_path",
]
