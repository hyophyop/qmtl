"""Synthetic data generators for strategy testing."""

from .base import SyntheticInput
from .garch import GarchInput
from .heston import HestonInput
from .rough_bergomi import RoughBergomiInput

__all__ = [
    "SyntheticInput",
    "GarchInput",
    "HestonInput",
    "RoughBergomiInput",
]
