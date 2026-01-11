"""Exit engine rule evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .config import ExitEngineConfig
from .models import ExitAction


def _select_action(world_id: str, config: ExitEngineConfig) -> str | None:
    if world_id in config.drain_world_ids:
        return "drain"
    if world_id in config.freeze_world_ids:
        return "freeze"
    return None


def _pick_strategy_id(snapshot: Mapping[str, Any], config: ExitEngineConfig) -> str | None:
    if config.strategy_id:
        return config.strategy_id
    weights = snapshot.get("weights")
    if not isinstance(weights, Mapping):
        return None
    best: tuple[str, float] | None = None
    for key, value in weights.items():
        try:
            weight = float(value)
        except Exception:
            continue
        if best is None or weight > best[1]:
            best = (str(key), weight)
    return best[0] if best else None


def _resolve_run_id(snapshot: Mapping[str, Any]) -> str:
    for key in ("run_id", "version", "hash"):
        value = snapshot.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def determine_exit_action(
    snapshot: Mapping[str, Any],
    config: ExitEngineConfig,
    *,
    request_id: str | None = None,
) -> ExitAction | None:
    world_id = str(snapshot.get("world_id") or "").strip()
    if not world_id:
        return None
    action = _select_action(world_id, config)
    if action is None:
        return None
    strategy_id = _pick_strategy_id(snapshot, config)
    if not strategy_id:
        return None
    run_id = _resolve_run_id(snapshot)
    resolved_request_id = request_id or str(snapshot.get("hash") or run_id or "")
    reason = f"{config.reason}:{action}"
    return ExitAction(
        world_id=world_id,
        strategy_id=strategy_id,
        side=config.side,
        action=action,
        reason=reason,
        run_id=run_id,
        request_id=str(resolved_request_id),
    )


__all__ = ["determine_exit_action"]
