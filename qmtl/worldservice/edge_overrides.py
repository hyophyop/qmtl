"""Edge override management for apply gating scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Tuple

from .policy import GatingPolicy
from .storage import EXECUTION_DOMAINS, Storage


@dataclass(slots=True)
class EdgeOverridePlan:
    """Normalized instructions derived from a gating policy."""

    pre_disable: List[str] = field(default_factory=list)
    post_enable: List[str] = field(default_factory=list)


class EdgeOverrideManager:
    """Manage edge overrides while recording previous state for restoration."""

    def __init__(self, store: Storage, world_id: str) -> None:
        self.store = store
        self.world_id = world_id
        self._restore: Dict[Tuple[str, str], Dict[str, Any] | None] = {}

    @staticmethod
    def plan_for(gating: GatingPolicy | None) -> EdgeOverridePlan:
        if not isinstance(gating, GatingPolicy):
            return EdgeOverridePlan()
        return EdgeOverridePlan(
            pre_disable=EdgeOverrideManager._coerce_edge_targets(
                gating.edges.pre_promotion.disable_edges_to
            ),
            post_enable=EdgeOverrideManager._coerce_edge_targets(
                gating.edges.post_promotion.enable_edges_to
            ),
        )

    async def apply_pre_promotion(self, domains: Iterable[str], run_id: str) -> None:
        for domain in domains:
            await self._set_edge_override(
                domain,
                active=False,
                reason=f"pre_promotion_disable:{run_id}",
            )

    async def apply_post_promotion(self, domains: Iterable[str], run_id: str) -> None:
        for domain in domains:
            await self._set_edge_override(
                domain,
                active=True,
                reason=f"post_promotion_enable:{run_id}",
            )

    async def restore(self) -> None:
        if not self._restore:
            return
        for (src_node_id, dst_node_id), previous in self._restore.items():
            if previous is None:
                await self.store.delete_edge_override(
                    self.world_id, src_node_id, dst_node_id
                )
            else:
                await self.store.upsert_edge_override(
                    self.world_id,
                    src_node_id,
                    dst_node_id,
                    active=bool(previous.get("active", False)),
                    reason=previous.get("reason"),
                )

    async def _set_edge_override(
        self,
        domain: str,
        *,
        active: bool,
        reason: str | None,
    ) -> None:
        src_node_id = "domain:backtest"
        dst_node_id = f"domain:{domain}"
        key = (src_node_id, dst_node_id)
        if key not in self._restore:
            self._restore[key] = await self.store.get_edge_override(
                self.world_id, src_node_id, dst_node_id
            )
        await self.store.upsert_edge_override(
            self.world_id,
            src_node_id,
            dst_node_id,
            active=active,
            reason=reason,
        )

    @staticmethod
    def _coerce_edge_targets(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates: Iterable[str] = [value]
        else:
            candidates = list(value)
        normalized = {EdgeOverrideManager._normalize_edge_domain(item) for item in candidates}
        return sorted(normalized)

    @staticmethod
    def _normalize_edge_domain(candidate: str) -> str:
        domain = str(candidate).strip().lower()
        if not domain:
            raise ValueError("edge override domain cannot be empty")
        if domain not in EXECUTION_DOMAINS:
            raise ValueError(f"unknown execution domain for edge override: {candidate}")
        return domain


__all__ = ["EdgeOverrideManager", "EdgeOverridePlan"]
