"""Shared compute context helpers for strategy submissions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, List

from qmtl.foundation.common.compute_context import (
    ComputeContext,
    DowngradeReason,
    build_strategy_compute_context,
    build_worldservice_compute_context,
)
from qmtl.services.gateway import metrics as gw_metrics

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from qmtl.services.gateway.models import StrategySubmit
    from qmtl.services.gateway.world_client import WorldServiceClient


class _WorldDecisionUnavailable(RuntimeError):
    """Sentinel exception representing a failed WorldService lookup."""

    def __init__(self, world_id: str, *, stale: bool = False) -> None:
        super().__init__(f"world decision unavailable for {world_id}")
        self.world_id = world_id
        self.stale = stale


@dataclass(frozen=True)
class StrategyComputeContext:
    """Value object capturing normalized strategy compute context."""

    context: ComputeContext
    worlds: tuple[str, ...]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.context, name)

    def diff_kwargs(self) -> dict[str, str | None]:
        return self.context.diff_kwargs()

    def commit_log_payload(self) -> dict[str, Any]:
        return self.context.to_dict(include_flags=True)

    def redis_mapping(self) -> dict[str, str]:
        payload = self.commit_log_payload()
        return {
            f"compute_{k}": v
            for k, v in payload.items()
            if isinstance(v, str) and v
        }

    def worlds_list(self) -> list[str]:
        return list(self.worlds)

    def primary_world(self) -> str | None:
        return self.worlds[0] if self.worlds else None


class ComputeContextService:
    """Normalize compute context metadata and world identifiers."""

    def __init__(self, world_client: "WorldServiceClient | None" = None) -> None:
        self._world_client = world_client

    async def build(
        self, payload: "StrategySubmit"
    ) -> StrategyComputeContext:
        worlds = tuple(self._unique_worlds(payload))
        meta = payload.meta if isinstance(payload.meta, dict) else None
        base_ctx = build_strategy_compute_context(meta)

        context = base_ctx
        if worlds:
            context = context.with_world(worlds[0])

        decision_ctx: ComputeContext | None = None
        stale_decision = False
        downgrade_missing_decision = False
        if worlds and self._world_client is not None:
            world_id = worlds[0]
            try:
                decision_ctx, stale_decision = await self._fetch_decision_context(world_id)
            except _WorldDecisionUnavailable as exc:
                stale_decision = stale_decision or exc.stale
                decision_ctx = None
                downgrade_missing_decision = True

        if decision_ctx is not None:
            context = self._merge_contexts(decision_ctx, base_ctx)
            if stale_decision:
                context = self._downgrade_stale(context)
        elif downgrade_missing_decision and worlds:
            gw_metrics.record_worlds_stale_response()
            if not context.safe_mode:
                context = self._downgrade_unavailable(context)

        return StrategyComputeContext(context=context, worlds=worlds)

    async def _fetch_decision_context(
        self, world_id: str
    ) -> tuple[ComputeContext | None, bool]:
        if self._world_client is None:
            raise _WorldDecisionUnavailable(world_id)
        try:
            payload, stale = await self._world_client.get_decide(world_id)
        except Exception as exc:  # pragma: no cover - defensive network guard
            raise _WorldDecisionUnavailable(world_id) from exc
        if payload is None:
            raise _WorldDecisionUnavailable(world_id, stale=stale)
        try:
            context = build_worldservice_compute_context(world_id, payload)
        except Exception as exc:  # pragma: no cover - protect against schema drift
            raise _WorldDecisionUnavailable(world_id, stale=stale) from exc
        return context, stale

    def _merge_contexts(
        self, decision_ctx: ComputeContext, base_ctx: ComputeContext
    ) -> ComputeContext:
        overrides: dict[str, Any] = {}
        if base_ctx.partition:
            overrides["partition"] = base_ctx.partition
        if base_ctx.as_of and not decision_ctx.as_of:
            overrides["as_of"] = base_ctx.as_of
        if overrides:
            decision_ctx = decision_ctx.with_overrides(**overrides)
        return decision_ctx

    def _downgrade_stale(self, context: ComputeContext) -> ComputeContext:
        downgraded = context.with_overrides(execution_domain="backtest", as_of=None)
        return replace(
            downgraded,
            downgraded=True,
            downgrade_reason=DowngradeReason.STALE_DECISION,
            safe_mode=True,
        )

    def _downgrade_unavailable(self, context: ComputeContext) -> ComputeContext:
        current_domain = (context.execution_domain or "").lower()
        target_domain = "backtest" if current_domain != "dryrun" else "dryrun"
        downgraded = context.with_overrides(execution_domain=target_domain)
        reason = context.downgrade_reason or DowngradeReason.DECISION_UNAVAILABLE
        return replace(
            downgraded,
            downgraded=True,
            downgrade_reason=reason,
            safe_mode=True,
        )

    def _unique_worlds(self, payload: "StrategySubmit") -> List[str]:
        candidates: list[str] = []
        if payload.world_id:
            candidates.append(str(payload.world_id))
        wid_list = getattr(payload, "world_ids", None)
        if wid_list:
            candidates.extend(str(item) for item in wid_list if item)
        unique: list[str] = []
        seen: set[str] = set()
        for value in candidates:
            normalized = self._normalize(value)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
        return unique

    def _normalize(self, value: Any | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode()
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            return text or None
        return None


__all__ = ["ComputeContextService", "StrategyComputeContext"]
