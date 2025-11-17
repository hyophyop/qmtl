from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class _EdgeDirective(BaseModel):
    disable_edges_to: list[str] | str | None = None
    enable_edges_to: list[str] | str | None = None


class _SnapshotConfig(BaseModel):
    strategy_plane: str
    feature_plane: str


class _SLOConfig(BaseModel):
    cross_context_cache_hit: int = Field(ge=0)

    @field_validator("cross_context_cache_hit")
    @classmethod
    def _ensure_zero(cls, value: int) -> int:
        if value != 0:
            raise ValueError("observability.slo.cross_context_cache_hit must equal 0")
        return value


class _ObservabilityConfig(BaseModel):
    slo: _SLOConfig


class _EdgesConfig(BaseModel):
    pre_promotion: _EdgeDirective
    post_promotion: _EdgeDirective


class GatingPolicy(BaseModel):
    dataset_fingerprint: str
    share_policy: str
    snapshot: _SnapshotConfig
    edges: _EdgesConfig
    observability: _ObservabilityConfig

    @field_validator("share_policy")
    @classmethod
    def _share_policy_required(cls, value: str) -> str:
        if value != "feature-artifacts-only":
            raise ValueError("share_policy must be 'feature-artifacts-only'")
        return value


def parse_gating_policy(raw: Any) -> GatingPolicy:
    """Parse and validate a gating policy document.

    Args:
        raw: Mapping, YAML/JSON string or bytes describing a gating policy.

    Returns:
        A :class:`GatingPolicy` instance with normalized data.

    Raises:
        ValueError: If the policy is missing required fields or violates constraints.
    """

    if raw is None:
        raise ValueError("gating_policy payload is required")

    data: Any = raw
    if isinstance(raw, (str, bytes)):
        data = yaml.safe_load(raw)

    if not isinstance(data, dict):
        raise ValueError("gating_policy must be a mapping")

    policy = data.get("gating_policy") if "gating_policy" in data else data

    if not isinstance(policy, dict):
        raise ValueError("gating_policy must be a mapping")

    try:
        return GatingPolicy.model_validate(policy)
    except ValidationError as exc:  # pragma: no cover - pydantic formats message
        raise ValueError(exc.errors()[0]["msg"]) from exc


__all__ = ["GatingPolicy", "parse_gating_policy"]
