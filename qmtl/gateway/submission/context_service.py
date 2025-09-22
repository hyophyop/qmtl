from __future__ import annotations

"""Shared compute context helpers for strategy submissions."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List

from qmtl.common.compute_context import ComputeContext, build_strategy_compute_context

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from qmtl.gateway.models import StrategySubmit


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

    def build(
        self, payload: "StrategySubmit"
    ) -> StrategyComputeContext:
        worlds = tuple(self._unique_worlds(payload))
        meta = payload.meta if isinstance(payload.meta, dict) else None
        base_ctx = build_strategy_compute_context(meta)
        context = base_ctx.with_world(worlds[0]) if worlds else base_ctx
        return StrategyComputeContext(context=context, worlds=worlds)

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
