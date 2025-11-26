"""Policy presets for QMTL v2.0.

This module re-exports the unified preset definitions from
qmtl.foundation.common.presets for backward compatibility.

Presets:
  sandbox       Development/testing only, no real execution
  conservative  Strict thresholds, limited positions
  moderate      Balanced risk/reward trade-off
  aggressive    Higher risk tolerance, more positions
"""

from __future__ import annotations

# Re-export everything from the unified preset module
from qmtl.foundation.common.presets import (
    PolicyPreset,
    PresetPolicy,
    ThresholdConfig,
    TopKConfig,
    HysteresisConfig,
    CorrelationConfig,
    get_preset,
    list_presets,
    PRESETS,
    PRESET_SANDBOX,
    PRESET_CONSERVATIVE,
    PRESET_MODERATE,
    PRESET_AGGRESSIVE,
)

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
