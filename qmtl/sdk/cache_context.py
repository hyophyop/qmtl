from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from qmtl.common.compute_key import DEFAULT_EXECUTION_DOMAIN


class MetricsObserver(Protocol):
    def observe_cross_context_cache_hit(
        self,
        node_id: str,
        world_id: str,
        execution_domain: str,
        *,
        as_of: str | None,
        partition: str | None,
    ) -> None:
        ...


@dataclass(frozen=True)
class ComputeContext:
    compute_key: str
    world_id: str
    execution_domain: str
    as_of: Any | None
    partition: Any | None


class ContextSwitchStrategy:
    """Track the active compute context and emit metrics when it changes."""

    def __init__(self, metrics: MetricsObserver) -> None:
        self._metrics = metrics
        self._active: ComputeContext | None = None

    @staticmethod
    def _normalize(
        compute_key: str | None,
        *,
        world_id: str | None,
        execution_domain: str | None,
        as_of: Any | None,
        partition: Any | None,
    ) -> ComputeContext:
        key = compute_key or "__default__"
        world = str(world_id or "")
        domain = str(execution_domain or DEFAULT_EXECUTION_DOMAIN)
        return ComputeContext(key, world, domain, as_of, partition)

    @property
    def active(self) -> ComputeContext | None:
        return self._active

    def ensure(
        self,
        compute_key: str | None,
        *,
        node_id: str,
        world_id: str | None = None,
        execution_domain: str | None = None,
        as_of: Any | None = None,
        partition: Any | None = None,
        had_data: bool = False,
    ) -> tuple[ComputeContext, bool]:
        """Ensure the context is up to date, returning (context, cleared)."""

        context = self._normalize(
            compute_key,
            world_id=world_id,
            execution_domain=execution_domain,
            as_of=as_of,
            partition=partition,
        )
        if self._active is None:
            self._active = context
            return context, False
        if self._active.compute_key == context.compute_key:
            # Reuse existing buffer when only metadata changes.
            self._active = context
            return context, False

        cleared = self._active.compute_key != context.compute_key
        if cleared and had_data:
            self._metrics.observe_cross_context_cache_hit(
                node_id,
                context.world_id,
                context.execution_domain,
                as_of=str(context.as_of) if context.as_of is not None else None,
                partition=(
                    str(context.partition) if context.partition is not None else None
                ),
            )
        self._active = context
        return context, cleared


__all__ = ["ContextSwitchStrategy", "ComputeContext"]
