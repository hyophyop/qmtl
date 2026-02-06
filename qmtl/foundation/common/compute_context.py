from __future__ import annotations

"""Canonical compute context model shared across QMTL services."""

from dataclasses import dataclass, replace
from enum import Enum
import re
from typing import Any, Mapping

__all__ = [
    "DEFAULT_EXECUTION_DOMAIN",
    "ComputeContext",
    "DowngradeReason",
    "normalize_context_value",
    "resolve_execution_domain",
    "evaluate_safe_mode",
    "build_strategy_compute_context",
    "build_worldservice_compute_context",
    "coerce_compute_context",
    "canonicalize_world_mode",
]

DEFAULT_EXECUTION_DOMAIN = "default"
_COMPUTE_ONLY_DOMAIN = "backtest"

_BACKTEST_TOKENS = {
    "backtest",
    "backtesting",
    "compute",
    "computeonly",
    "offline",
    "sandbox",
    "validate",
    "validation",
}
_DRYRUN_TOKENS = {
    "dryrun",
    "dryrunmode",
    "papermode",
    "paper",
    "papertrade",
    "papertrading",
    "papertrader",
    "sim",
    "simulation",
    "simulated",
}
_LIVE_TOKENS = {"live", "prod", "production"}
_SHADOW_TOKENS = {"shadow"}

_CANONICAL_WORLD_MODE_TO_DOMAIN = {
    "validate": "backtest",
    "compute-only": "backtest",
    "paper": "dryrun",
    "live": "live",
    "shadow": "shadow",
}

_WORLD_MODE_ALIASES = {
    "validate": "validate",
    "compute-only": "compute-only",
    "compute_only": "compute-only",
    "computeonly": "compute-only",
    "paper": "paper",
    "sim": "paper",
    "simulation": "paper",
    "simulated": "paper",
    "papertrade": "paper",
    "papertrading": "paper",
    "paper_trading": "paper",
    "live": "live",
    "active": "live",
    "shadow": "shadow",
}

_WORLD_MODE_TOKENS = {
    alias: _CANONICAL_WORLD_MODE_TO_DOMAIN[canonical]
    for alias, canonical in _WORLD_MODE_ALIASES.items()
}


class DowngradeReason(str, Enum):
    """Enumerate downgrade reasons shared across services."""

    MISSING_AS_OF = "missing_as_of"
    STALE_DECISION = "stale_decision"
    DECISION_UNAVAILABLE = "decision_unavailable"


def normalize_context_value(value: Any | None) -> str | None:
    """Normalize raw values into stripped strings."""

    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def _normalize_optional(value: Any | None) -> str | None:
    normalized = normalize_context_value(value)
    return normalized


def resolve_execution_domain(value: str | None) -> str | None:
    """Map execution domain aliases to canonical tokens."""

    if value is None:
        return None
    lowered = value.lower()
    segments = re.split(r"[/:]", lowered)
    for segment in segments:
        token = re.sub(r"[\s_-]+", "", segment)
        if token in _BACKTEST_TOKENS:
            return "backtest"
        if token in _DRYRUN_TOKENS:
            return "dryrun"
        if token in _LIVE_TOKENS:
            return "live"
        if token in _SHADOW_TOKENS:
            return "shadow"
    return lowered


def _is_missing_execution_domain(value: str | None) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return text.lower() == DEFAULT_EXECUTION_DOMAIN


def evaluate_safe_mode(
    execution_domain: str | None, as_of: str | None
) -> tuple[str | None, bool, DowngradeReason | None, bool]:
    """Determine downgrades and safe-mode requirements."""

    downgraded = False
    downgrade_reason: DowngradeReason | None = None
    safe_mode = False

    if _is_missing_execution_domain(execution_domain):
        downgraded = True
        downgrade_reason = DowngradeReason.DECISION_UNAVAILABLE
        safe_mode = True
        execution_domain = _COMPUTE_ONLY_DOMAIN
    else:
        domain = str(execution_domain).strip().lower()
        if domain in {"backtest", "dryrun"} and not as_of:
            downgraded = True
            downgrade_reason = DowngradeReason.MISSING_AS_OF
            safe_mode = True
            execution_domain = _COMPUTE_ONLY_DOMAIN
        else:
            execution_domain = domain

    return execution_domain, downgraded, downgrade_reason, safe_mode


@dataclass(frozen=True)
class ComputeContext:
    """Immutable compute context representation."""

    world_id: str = ""
    execution_domain: str = DEFAULT_EXECUTION_DOMAIN
    as_of: str | None = None
    partition: str | None = None
    dataset_fingerprint: str | None = None
    downgraded: bool = False
    downgrade_reason: DowngradeReason | None = None
    safe_mode: bool = False

    def __post_init__(self) -> None:
        final_domain, downgraded, reason, safe_mode = evaluate_safe_mode(
            self.execution_domain, self.as_of
        )
        if final_domain != self.execution_domain:
            object.__setattr__(self, "execution_domain", final_domain or "")
        if downgraded and not self.downgraded:
            object.__setattr__(self, "downgraded", True)
        if reason is not None and self.downgrade_reason is None:
            object.__setattr__(self, "downgrade_reason", reason)
        if safe_mode and not self.safe_mode:
            object.__setattr__(self, "safe_mode", True)

    def with_world(self, world_id: str | None) -> "ComputeContext":
        return replace(self, world_id=_normalize_optional(world_id) or "")

    def with_overrides(
        self,
        *,
        execution_domain: str | None = None,
        as_of: str | None = None,
        partition: str | None = None,
        dataset_fingerprint: str | None = None,
    ) -> "ComputeContext":
        domain_value = self.execution_domain
        if execution_domain is not None:
            domain_value = resolve_execution_domain(_normalize_optional(execution_domain)) or ""

        as_of_value = self.as_of if as_of is None else _normalize_optional(as_of)
        partition_value = self.partition if partition is None else _normalize_optional(partition)
        dataset_value = (
            self.dataset_fingerprint
            if dataset_fingerprint is None
            else _normalize_optional(dataset_fingerprint)
        )

        final_domain, downgraded, reason, safe_mode = evaluate_safe_mode(
            domain_value or None,
            as_of_value,
        )
        return replace(
            self,
            execution_domain=(final_domain or ""),
            as_of=as_of_value,
            partition=partition_value,
            dataset_fingerprint=dataset_value,
            downgraded=downgraded,
            downgrade_reason=reason,
            safe_mode=safe_mode,
        )

    def to_dict(self, *, include_flags: bool = True, include_world: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "execution_domain": self.execution_domain or None,
            "as_of": self.as_of,
            "partition": self.partition,
            "dataset_fingerprint": self.dataset_fingerprint,
        }
        if include_world:
            payload["world_id"] = self.world_id or None
        if include_flags and self.downgraded:
            payload["downgraded"] = True
            if self.downgrade_reason:
                payload["downgrade_reason"] = self.downgrade_reason.value
            if self.safe_mode:
                payload["safe_mode"] = True
        elif include_flags and self.safe_mode:
            payload["safe_mode"] = True
        return payload

    def diff_kwargs(self) -> dict[str, str | None]:
        return {
            "execution_domain": self.execution_domain or None,
            "as_of": self.as_of,
            "partition": self.partition,
            "dataset_fingerprint": self.dataset_fingerprint,
        }

    def metrics_labels(self) -> tuple[str, str, str | None, str | None]:
        domain = self.execution_domain or ""
        if _is_missing_execution_domain(domain):
            domain = _COMPUTE_ONLY_DOMAIN
        return (self.world_id or "", domain, self.as_of, self.partition)

    def hash_components(self) -> tuple[str, str, str, str]:
        world = self.world_id or ""
        domain = self.execution_domain or ""
        if _is_missing_execution_domain(domain):
            domain = _COMPUTE_ONLY_DOMAIN
        as_of = "" if self.as_of is None else str(self.as_of)
        partition = "" if self.partition is None else str(self.partition)
        return world, domain, as_of, partition


def _initial_context(
    *,
    world_id: Any | None,
    execution_domain: Any | None,
    as_of: Any | None,
    partition: Any | None,
    dataset_fingerprint: Any | None,
) -> ComputeContext:
    world = _normalize_optional(world_id) or ""
    domain = resolve_execution_domain(_normalize_optional(execution_domain))
    as_of_norm = _normalize_optional(as_of)
    partition_norm = _normalize_optional(partition)
    dataset_norm = _normalize_optional(dataset_fingerprint)
    final_domain, downgraded, reason, safe_mode = evaluate_safe_mode(
        domain, as_of_norm
    )
    return ComputeContext(
        world_id=world,
        execution_domain=(final_domain or ""),
        as_of=as_of_norm,
        partition=partition_norm,
        dataset_fingerprint=dataset_norm,
        downgraded=downgraded,
        downgrade_reason=reason,
        safe_mode=safe_mode,
    )


def build_strategy_compute_context(meta: Mapping[str, Any] | None) -> ComputeContext:
    """Derive compute context from submission metadata."""

    meta = meta or {}
    dataset = meta.get("dataset_fingerprint") or meta.get("datasetFingerprint")
    return _initial_context(
        world_id=None,
        execution_domain=meta.get("execution_domain"),
        as_of=meta.get("as_of"),
        partition=meta.get("partition"),
        dataset_fingerprint=dataset,
    )


def canonicalize_world_mode(value: Any | None) -> str:
    """Normalize world policy modes to the canonical vocabulary."""

    if not isinstance(value, str):
        return "validate"
    token = value.strip().lower()
    if not token:
        return "validate"
    return _WORLD_MODE_ALIASES.get(token, "validate")


def _resolve_world_mode(value: Any | None) -> str:
    canonical = canonicalize_world_mode(value)
    return _CANONICAL_WORLD_MODE_TO_DOMAIN.get(canonical, "backtest")


def build_worldservice_compute_context(
    world_id: str, payload: Mapping[str, Any]
) -> ComputeContext:
    """Derive compute context from a WorldService decision payload."""

    domain = _resolve_world_mode(payload.get("effective_mode"))
    as_of = payload.get("as_of")
    partition = payload.get("partition")
    dataset = payload.get("dataset_fingerprint") or payload.get("datasetFingerprint")
    context = _initial_context(
        world_id=world_id,
        execution_domain=domain,
        as_of=as_of,
        partition=partition,
        dataset_fingerprint=dataset,
    )
    return context


def coerce_compute_context(payload: Mapping[str, Any] | None) -> ComputeContext:
    """Coerce a loosely-typed payload into :class:`ComputeContext`."""

    payload = payload or {}
    dataset = payload.get("dataset_fingerprint") or payload.get("datasetFingerprint")
    return _initial_context(
        world_id=payload.get("world_id") or payload.get("world"),
        execution_domain=payload.get("execution_domain") or payload.get("domain"),
        as_of=payload.get("as_of"),
        partition=payload.get("partition"),
        dataset_fingerprint=dataset,
    )
