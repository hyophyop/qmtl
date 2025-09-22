from __future__ import annotations

"""Shared compute context helpers for strategy submissions."""

from typing import TYPE_CHECKING, Any, Dict, List

from qmtl.common.compute_context import ComputeContext, build_strategy_compute_context

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from qmtl.gateway.models import StrategySubmit


class ComputeContextService:
    """Normalize compute context metadata and world identifiers."""

    def build(
        self, payload: "StrategySubmit"
    ) -> tuple[ComputeContext, Dict[str, Any], Dict[str, str], List[str]]:
        worlds = self._unique_worlds(payload)
        meta = payload.meta if isinstance(payload.meta, dict) else None
        base_ctx = build_strategy_compute_context(meta)
        context = base_ctx.with_world(worlds[0]) if worlds else base_ctx
        context_payload = context.to_dict(include_flags=True)
        context_mapping = {
            f"compute_{k}": v
            for k, v in context_payload.items()
            if isinstance(v, str) and v
        }
        return context, context_payload, context_mapping, worlds

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
