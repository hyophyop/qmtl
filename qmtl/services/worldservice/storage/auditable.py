"""Shared audit helpers for worldservice repositories."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class AuditSink(Protocol):
    """Protocol describing the minimal audit interface repositories depend on."""

    def append(self, world_id: str, entry: Mapping[str, Any]) -> None:
        """Persist an audit entry for *world_id*."""


class AuditableRepository:
    """Base class that stores an :class:`AuditSink` and normalises audit payloads."""

    def __init__(self, audit: AuditSink) -> None:
        self._audit = audit

    @property
    def audit(self) -> AuditSink:
        """Return the configured audit sink."""

        return self._audit

    def _emit_audit(self, world_id: str, payload: Mapping[str, Any]) -> None:
        """Send a shallow copy of *payload* to the audit sink."""

        self._audit.append(world_id, dict(payload))


__all__ = ["AuditSink", "AuditableRepository"]
