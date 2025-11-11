"""Auto-generated adapter for the intent-first NodeSet recipe."""

from qmtl.runtime.nodesets.adapter import NodeSetAdapter
from qmtl.runtime.nodesets.recipes import INTENT_FIRST_ADAPTER_SPEC, build_adapter

IntentFirstAdapter: type[NodeSetAdapter] = build_adapter(INTENT_FIRST_ADAPTER_SPEC)

__all__ = ["IntentFirstAdapter"]
