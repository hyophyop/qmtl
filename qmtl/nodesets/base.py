from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qmtl.sdk.node import Node

from .options import NodeSetOptions
from .stubs import (
    StubPreTradeGateNode,
    StubSizingNode,
    StubExecutionNode,
    StubFillIngestNode,
    StubPortfolioNode,
    StubRiskControlNode,
    StubTimingGateNode,
)


@dataclass(frozen=True)
class NodeSet:
    pretrade: Node
    sizing: Node
    execution: Node
    fills: Node
    portfolio: Node
    risk: Node
    timing: Node


class NodeSetBuilder:
    """Compose a minimal execution chain behind a signal node.

    This initial scaffold wires pass-through stubs to establish contracts and
    integration points. Concrete Node Sets will replace these with real nodes
    and options.
    """

    def __init__(self, *, options: NodeSetOptions | None = None) -> None:
        self.options = options or NodeSetOptions()

    def attach(self, signal: Node, *, world_id: str, scope: Literal["strategy", "world"] = "strategy") -> NodeSet:
        # For scaffolding, all stubs inherit the interval from the signal node
        pre = StubPreTradeGateNode(signal)
        siz = StubSizingNode(pre)
        exe = StubExecutionNode(siz)
        fil = StubFillIngestNode(exe)
        pf = StubPortfolioNode(fil)
        rk = StubRiskControlNode(pf)
        tm = StubTimingGateNode(rk)
        return NodeSet(pretrade=pre, sizing=siz, execution=exe, fills=fil, portfolio=pf, risk=rk, timing=tm)


__all__ = ["NodeSetBuilder", "NodeSet"]

