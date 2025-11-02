"""Example modules for QMTL."""

import sys

# Create qmtl.examples module
sys.modules['qmtl.examples'] = sys.modules[__name__]

from . import dags

__all__: list[str] = []
