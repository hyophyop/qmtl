"""Signal strategy provider.

This module exports the strategy creation function.
"""

from __future__ import annotations

# Import the default template
from .single_indicator import create_strategy

__all__ = ["create_strategy"]
