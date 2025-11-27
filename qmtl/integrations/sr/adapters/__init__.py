"""SR engine adapters package.

This package provides adapters for various SR (Strategy Recommendation) engines
to convert their outputs into QMTL-compatible formats.

Available Adapters:
- generic: Generic adapter for any SR engine that produces expression strings
- operon: Adapter for Operon/pyoperon GP engine (requires pyoperon)
"""

from .generic import GenericSRAdapter, GenericCandidate  # noqa: F401

# Operon adapter is optional - only import if pyoperon is available
try:
    from .operon import OperonAdapter, OperonCandidate  # noqa: F401

    _OPERON_AVAILABLE = True
except ImportError:
    _OPERON_AVAILABLE = False

__all__ = [
    "GenericSRAdapter",
    "GenericCandidate",
    "OperonAdapter",
    "OperonCandidate",
]
