"""Unified preset policy definitions for QMTL.

This module provides a single source of truth for policy presets used by
both the SDK and WorldService. All preset definitions should be imported
from here to avoid drift between client and server.

Presets:
  sandbox       Development/testing only, no real execution
  conservative  Strict thresholds, limited positions
  moderate      Balanced risk/reward trade-off
  aggressive    Higher risk tolerance, more positions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional


class PolicyPreset(StrEnum):
    """Available policy preset levels."""

    SANDBOX = "sandbox"
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class ThresholdConfig:
    """Threshold rule configuration."""

    metric: str
    min: Optional[float] = None
    max: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"metric": self.metric}
        if self.min is not None:
            result["min"] = self.min
        if self.max is not None:
            result["max"] = self.max
        return result


@dataclass
class TopKConfig:
    """Top-K selection configuration."""

    metric: str
    k: int

    def to_dict(self) -> Dict[str, Any]:
        return {"metric": self.metric, "k": self.k}


@dataclass
class HysteresisConfig:
    """Hysteresis rule configuration."""

    metric: str
    enter: float
    exit: float

    def to_dict(self) -> Dict[str, Any]:
        return {"metric": self.metric, "enter": self.enter, "exit": self.exit}


@dataclass
class CorrelationConfig:
    """Correlation constraint configuration."""

    max: float

    def to_dict(self) -> Dict[str, Any]:
        return {"max": self.max}


@dataclass
class PresetPolicy:
    """Complete policy configuration from a preset.

    This is a simplified representation that can be converted to
    the full Policy format used by WorldService.
    """

    name: str
    description: str
    allow_live: bool = False
    max_strategies: int = 1
    thresholds: List[ThresholdConfig] = field(default_factory=list)
    top_k: Optional[TopKConfig] = None
    correlation: Optional[CorrelationConfig] = None
    hysteresis: Optional[HysteresisConfig] = None

    def to_policy_dict(self) -> Dict[str, Any]:
        """Convert to Policy-compatible dict for WorldService."""
        result: Dict[str, Any] = {}

        if self.thresholds:
            result["thresholds"] = {t.metric: t.to_dict() for t in self.thresholds}

        if self.top_k:
            result["top_k"] = self.top_k.to_dict()

        if self.correlation:
            result["correlation"] = self.correlation.to_dict()

        if self.hysteresis:
            result["hysteresis"] = self.hysteresis.to_dict()

        return result

    def to_yaml(self) -> str:
        """Convert to YAML string for storage."""
        import yaml

        data = {
            "name": self.name,
            "description": self.description,
            "allow_live": self.allow_live,
            "max_strategies": self.max_strategies,
            **self.to_policy_dict(),
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True)


# ============================================================================
# Preset Definitions (Single Source of Truth)
# ============================================================================

PRESET_SANDBOX = PresetPolicy(
    name="sandbox",
    description="Development and testing only. No real execution allowed.",
    allow_live=False,
    max_strategies=10,
    thresholds=[],  # No threshold requirements - accept all for testing
    top_k=TopKConfig(metric="sharpe", k=10),
)

PRESET_CONSERVATIVE = PresetPolicy(
    name="conservative",
    description="Strict thresholds and limited exposure. Safe for beginners.",
    allow_live=True,
    max_strategies=3,
    thresholds=[
        ThresholdConfig(metric="sharpe", min=1.0),
        ThresholdConfig(metric="max_drawdown", max=0.15),
        ThresholdConfig(metric="win_rate", min=0.55),
        ThresholdConfig(metric="profit_factor", min=1.5),
    ],
    top_k=TopKConfig(metric="sharpe", k=3),
    correlation=CorrelationConfig(max=0.5),
    hysteresis=HysteresisConfig(metric="sharpe", enter=1.0, exit=0.8),
)

PRESET_MODERATE = PresetPolicy(
    name="moderate",
    description="Balanced risk/reward. Good for established strategies.",
    allow_live=True,
    max_strategies=5,
    thresholds=[
        ThresholdConfig(metric="sharpe", min=0.7),
        ThresholdConfig(metric="max_drawdown", max=0.25),
        ThresholdConfig(metric="win_rate", min=0.50),
        ThresholdConfig(metric="profit_factor", min=1.2),
    ],
    top_k=TopKConfig(metric="sharpe", k=5),
    correlation=CorrelationConfig(max=0.7),
    hysteresis=HysteresisConfig(metric="sharpe", enter=0.7, exit=0.5),
)

PRESET_AGGRESSIVE = PresetPolicy(
    name="aggressive",
    description="Higher risk tolerance. For experienced users only.",
    allow_live=True,
    max_strategies=8,
    thresholds=[
        ThresholdConfig(metric="sharpe", min=0.5),
        ThresholdConfig(metric="max_drawdown", max=0.40),
        ThresholdConfig(metric="profit_factor", min=1.0),
    ],
    top_k=TopKConfig(metric="sharpe", k=8),
    correlation=CorrelationConfig(max=0.85),
    hysteresis=HysteresisConfig(metric="sharpe", enter=0.5, exit=0.3),
)

# Registry mapping preset names to policies
PRESETS: Dict[PolicyPreset, PresetPolicy] = {
    PolicyPreset.SANDBOX: PRESET_SANDBOX,
    PolicyPreset.CONSERVATIVE: PRESET_CONSERVATIVE,
    PolicyPreset.MODERATE: PRESET_MODERATE,
    PolicyPreset.AGGRESSIVE: PRESET_AGGRESSIVE,
}


def get_preset(preset: PolicyPreset | str) -> PresetPolicy:
    """Get a preset policy by name.

    Args:
        preset: Preset name or PolicyPreset enum value.

    Returns:
        PresetPolicy configuration.

    Raises:
        ValueError: If preset name is not recognized.
    """
    if isinstance(preset, str):
        try:
            preset = PolicyPreset(preset.lower())
        except ValueError:
            valid = ", ".join(p.value for p in PolicyPreset)
            raise ValueError(
                f"Unknown preset '{preset}'. Valid presets: {valid}"
            ) from None

    if preset not in PRESETS:
        valid = ", ".join(p.value for p in PolicyPreset)
        raise ValueError(f"Unknown preset '{preset}'. Valid presets: {valid}")

    return PRESETS[preset]


def list_presets() -> List[Dict[str, Any]]:
    """List all available presets with their descriptions.

    Returns:
        List of preset info dictionaries.
    """
    return [
        {
            "name": preset.value,
            "description": policy.description,
            "allow_live": policy.allow_live,
            "max_strategies": policy.max_strategies,
        }
        for preset, policy in PRESETS.items()
    ]


__all__ = [
    "PolicyPreset",
    "PresetPolicy",
    "ThresholdConfig",
    "TopKConfig",
    "HysteresisConfig",
    "CorrelationConfig",
    "get_preset",
    "list_presets",
    "PRESETS",
    "PRESET_SANDBOX",
    "PRESET_CONSERVATIVE",
    "PRESET_MODERATE",
    "PRESET_AGGRESSIVE",
]
