"""Compatibility wrappers for hazard utilities.

Import these helpers from :mod:`qmtl.transforms.hazard_utils`.
"""

from qmtl.transforms.hazard_utils import (
    hazard_probability,
    direction_signal,
    execution_cost,
)

__all__ = ["hazard_probability", "direction_signal", "execution_cost"]
