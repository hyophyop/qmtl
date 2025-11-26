"""Preset policy definitions for WorldService-side consumption.

This module provides WorldService-compatible Policy objects from the
unified preset definitions in qmtl.foundation.common.presets.
"""

from __future__ import annotations

from qmtl.foundation.common.presets import (
    PolicyPreset,
    PresetPolicy,
    get_preset as _get_preset,
)

from .policy_engine import CorrelationRule, HysteresisRule, Policy, ThresholdRule, TopKRule


def _preset_to_policy(preset: PresetPolicy) -> Policy:
    """Convert PresetPolicy to WorldService Policy."""
    thresholds = {
        t.metric: ThresholdRule(metric=t.metric, min=t.min, max=t.max)
        for t in preset.thresholds
    }
    top_k = None
    if preset.top_k:
        top_k = TopKRule(metric=preset.top_k.metric, k=preset.top_k.k)
    correlation = None
    if preset.correlation:
        correlation = CorrelationRule(max=preset.correlation.max)
    hysteresis = None
    if preset.hysteresis:
        hysteresis = HysteresisRule(
            metric=preset.hysteresis.metric,
            enter=preset.hysteresis.enter,
            exit=preset.hysteresis.exit,
        )
    return Policy(
        thresholds=thresholds,
        top_k=top_k,
        correlation=correlation,
        hysteresis=hysteresis,
    )


def get_preset_policy(name: str, overrides: dict | None = None) -> Policy:
    """Return a Policy for the given preset name, with optional threshold overrides.
    
    Args:
        name: Preset name (sandbox, conservative, moderate, aggressive).
        overrides: Optional dict of threshold overrides in format {"metric.bound": value}.
    
    Returns:
        Policy object for WorldService.
    """
    preset = _get_preset(name)
    policy = _preset_to_policy(preset)

    if overrides:
        for path, value in overrides.items():
            if not isinstance(path, str):
                continue
            parts = path.split(".")
            if len(parts) != 2:
                continue
            metric, bound = parts
            thresh = policy.thresholds.get(metric)
            if not thresh:
                continue
            if bound == "min":
                thresh.min = float(value)
            elif bound == "max":
                thresh.max = float(value)

    return policy


__all__ = ["get_preset_policy"]
