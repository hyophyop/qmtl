"""Auto-generated adapter for the triple-barrier labeling NodeSet recipe."""

from qmtl.runtime.nodesets.adapter import NodeSetAdapter
from qmtl.runtime.nodesets.recipes import (
    LABELING_TRIPLE_BARRIER_ADAPTER_SPEC,
    build_adapter,
)

LabelingTripleBarrierAdapter: type[NodeSetAdapter] = build_adapter(
    LABELING_TRIPLE_BARRIER_ADAPTER_SPEC
)

__all__ = ["LabelingTripleBarrierAdapter"]

