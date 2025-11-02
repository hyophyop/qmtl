"""DAG strategy definitions."""

import sys

# Create qmtl.examples.dags module
sys.modules['qmtl.examples.dags'] = sys.modules[__name__]

__all__ = []  # Will be populated by the import above
