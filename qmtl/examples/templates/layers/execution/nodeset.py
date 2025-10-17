"""NodeSet-based execution pipeline.

This module provides a complete execution pipeline using NodeSet.
"""

from __future__ import annotations

from qmtl.runtime.sdk import Node
from qmtl.runtime.nodesets.steps import pretrade, sizing, execution, fills, portfolio


def create_execution_nodeset(signal_node: Node):
    """Create execution NodeSet from signal.

    Args:
        signal_node: Signal generation node

    Returns:
        NodeSet with execution pipeline
    """
    # Create execution pipeline
    pre = pretrade()(signal_node)
    siz = sizing()(pre)
    exe = execution()(siz)
    fil = fills()(exe)
    pf = portfolio()(fil)
    
    return pf


def attach_execution_to_strategy(strategy, signal_node: Node):
    """Attach execution nodes to strategy.

    Args:
        strategy: Strategy instance
        signal_node: Signal generation node
    """
    execution_node = create_execution_nodeset(signal_node)
    strategy.add_nodes([execution_node])
