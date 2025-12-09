from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Mapping, NamedTuple
from urllib.parse import urlparse

from . import runtime
from .submit import SubmitResult, _get_gateway_url, _normalize_world_id


class _RunCoordinates(NamedTuple):
    world_id: str
    strategy_id: str
    run_id: str
    gateway_url: str


class _ParsedRunRef(NamedTuple):
    world_id: str | None
    strategy_id: str | None
    run_id: str | None
    gateway_url: str | None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _parse_run_ref(ref: str) -> _ParsedRunRef:
    """Extract world/strategy/run identifiers and base URL from a run reference.

    Accepts both raw run_ids and fully-qualified URLs such as
    https://gw/worlds/{world}/strategies/{strategy}/runs/{run_id}.
    """
    parsed = urlparse(ref)
    if not (parsed.scheme and parsed.netloc):
        return _ParsedRunRef(world_id=None, strategy_id=None, run_id=None, gateway_url=None)

    parts = [p for p in parsed.path.split("/") if p]
    world_id = strategy_id = run_id = None
    base_parts: list[str] = []

    for idx, part in enumerate(parts):
        if part == "worlds" and idx + 1 < len(parts):
            world_id = parts[idx + 1]
            base_parts = parts[:idx]
        if part == "strategies" and idx + 1 < len(parts):
            strategy_id = parts[idx + 1]
        if part == "runs" and idx + 1 < len(parts):
            run_id = parts[idx + 1]

    if run_id is None and parts:
        run_id = parts[-1]

    base_path = "/" + "/".join(base_parts) if base_parts else ""
    base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}"
    return _ParsedRunRef(world_id=world_id, strategy_id=strategy_id, run_id=run_id, gateway_url=base_url)


def _resolve_coordinates(
    *,
    world: str | None,
    run_id: str | None,
    strategy_id: str | None,
    submit_result: SubmitResult | None,
    gateway_url: str | None,
) -> _RunCoordinates:
    run_ref = run_id or (submit_result.evaluation_run_url if submit_result else None) or (
        submit_result.evaluation_run_id if submit_result else None
    )
    if not run_ref:
        raise ValueError("run_id or submit_result with evaluation_run_id is required")

    parsed = _parse_run_ref(run_ref)
    resolved_world = world or (submit_result.world if submit_result else None) or parsed.world_id
    resolved_strategy = strategy_id or (submit_result.strategy_id if submit_result else None) or parsed.strategy_id
    resolved_run_id = parsed.run_id or run_ref

    if not resolved_world:
        raise ValueError("world is required (pass world explicitly or embed it in evaluation_run_url)")
    if not resolved_strategy:
        raise ValueError(
            "strategy_id is required (pass strategy_id explicitly or provide a SubmitResult/evaluation_run_url that "
            "contains it)"
        )

    normalized_world = _normalize_world_id(resolved_world)
    base_gateway_url = gateway_url or parsed.gateway_url or _get_gateway_url(normalized_world)

    return _RunCoordinates(
        world_id=normalized_world,
        strategy_id=resolved_strategy,
        run_id=resolved_run_id,
        gateway_url=base_gateway_url,
    )


def _run_ready(payload: Mapping[str, Any]) -> bool:
    summary = payload.get("summary")
    metrics = payload.get("metrics")
    if isinstance(summary, Mapping):
        if summary.get("status") or summary.get("recommended_stage"):
            return True
    if isinstance(metrics, Mapping) and bool(metrics):
        return True
    return False


@dataclass
class EvaluationRunStatus:
    """Snapshot of a WorldService EvaluationRun."""

    world_id: str
    strategy_id: str
    run_id: str
    summary: dict[str, Any]
    metrics: dict[str, Any]
    validation: dict[str, Any]
    stage: str | None = None
    risk_tier: str | None = None
    model_card_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def status(self) -> str | None:
        raw = self.summary.get("status") if isinstance(self.summary, Mapping) else None
        return str(raw) if raw is not None else None

    @property
    def recommended_stage(self) -> str | None:
        raw = self.summary.get("recommended_stage") if isinstance(self.summary, Mapping) else None
        return str(raw) if raw is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_id": self.world_id,
            "strategy_id": self.strategy_id,
            "run_id": self.run_id,
            "stage": self.stage,
            "risk_tier": self.risk_tier,
            "summary": dict(self.summary),
            "status": self.status,
            "recommended_stage": self.recommended_stage,
            "metrics": dict(self.metrics),
            "validation": dict(self.validation),
            "model_card_version": self.model_card_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        world_id: str,
        strategy_id: str,
        run_id: str,
    ) -> "EvaluationRunStatus":
        summary = _as_dict(payload.get("summary"))
        metrics = _as_dict(payload.get("metrics"))
        validation = _as_dict(payload.get("validation"))
        raw = dict(payload)
        raw.setdefault("world_id", world_id)
        raw.setdefault("strategy_id", strategy_id)
        raw.setdefault("run_id", run_id)

        return cls(
            world_id=world_id,
            strategy_id=strategy_id,
            run_id=run_id,
            summary=summary,
            metrics=metrics,
            validation=validation,
            stage=str(payload.get("stage")) if payload.get("stage") is not None else None,
            risk_tier=str(payload.get("risk_tier")) if payload.get("risk_tier") is not None else None,
            model_card_version=(
                str(payload.get("model_card_version")) if payload.get("model_card_version") is not None else None
            ),
            created_at=str(payload.get("created_at")) if payload.get("created_at") is not None else None,
            updated_at=str(payload.get("updated_at")) if payload.get("updated_at") is not None else None,
            raw=raw,
        )


async def wait_for_evaluation_run(
    *,
    gateway_client: Any,
    world: str | None = None,
    run_id: str | None = None,
    strategy_id: str | None = None,
    submit_result: SubmitResult | None = None,
    gateway_url: str | None = None,
    timeout: float | None = 300.0,
    interval: float | None = None,
) -> EvaluationRunStatus:
    """Poll Gateway/WorldService for an EvaluationRun until summary/metrics are available."""

    coords = _resolve_coordinates(
        world=world,
        run_id=run_id,
        strategy_id=strategy_id,
        submit_result=submit_result,
        gateway_url=gateway_url,
    )

    poll_interval = runtime.POLL_INTERVAL_SECONDS if interval is None else float(max(interval, 0.0))
    deadline = time.monotonic() + float(timeout) if timeout is not None else None
    last_payload: Mapping[str, Any] | None = None

    while True:
        payload = await gateway_client.get_evaluation_run(
            gateway_url=coords.gateway_url,
            world_id=coords.world_id,
            strategy_id=coords.strategy_id,
            run_id=coords.run_id,
        )
        if isinstance(payload, Mapping):
            last_payload = payload
            if "error" in payload:
                raise RuntimeError(f"gateway error fetching evaluation run: {payload['error']}")
            if _run_ready(payload):
                return EvaluationRunStatus.from_payload(
                    payload,
                    world_id=coords.world_id,
                    strategy_id=coords.strategy_id,
                    run_id=coords.run_id,
                )
        elif payload is None:
            last_payload = None
        else:
            last_payload = None

        now = time.monotonic()
        if deadline is not None and now >= deadline:
            status_hint = None
            if isinstance(last_payload, Mapping):
                summary = last_payload.get("summary")
                if isinstance(summary, Mapping):
                    status_hint = summary.get("status")
            raise TimeoutError(
                f"Timed out waiting for evaluation run {coords.run_id} in world {coords.world_id}; "
                f"last_status={status_hint or 'unknown'}"
            )

        await asyncio.sleep(poll_interval)


__all__ = ["EvaluationRunStatus", "wait_for_evaluation_run"]
