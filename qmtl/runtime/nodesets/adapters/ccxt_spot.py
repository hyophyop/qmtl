from __future__ import annotations

"""CCXT spot Node Set adapter."""

from qmtl.runtime.nodesets.adapter import NodeSetAdapter
from qmtl.runtime.nodesets.recipes import CCXT_SPOT_ADAPTER_SPEC, build_adapter


CcxtSpotAdapter: type[NodeSetAdapter] = build_adapter(CCXT_SPOT_ADAPTER_SPEC)
CcxtSpotAdapter.__module__ = __name__


__all__ = ["CcxtSpotAdapter"]
