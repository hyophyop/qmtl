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
    
    @property
    def head(self) -> Node:
        return self.pretrade

    @property
    def tail(self) -> Node:
        return self.timing

    @property
    def nodes(self) -> list[Node]:
        return [
            self.pretrade,
            self.sizing,
            self.execution,
            self.fills,
            self.portfolio,
            self.risk,
            self.timing,
        ]

    # Allow treating the NodeSet as an iterable of nodes so callers can pass
    # the whole set to Strategy.add_nodes without referencing internals.
    def __iter__(self):  # type: ignore[override]
        yield from self.nodes


class NodeSetBuilder:
    """Compose a minimal execution chain behind a signal node.

    This initial scaffold wires pass-through stubs to establish contracts and
    integration points. Concrete Node Sets will replace these with real nodes
    and options.
    """

    def __init__(self, *, options: NodeSetOptions | None = None) -> None:
        self.options = options or NodeSetOptions()

    def attach(
        self,
        signal: Node,
        *,
        world_id: str,
        scope: Literal["strategy", "world"] = "strategy",
        pretrade: Node | None = None,
        sizing: Node | None = None,
        execution: Node | None = None,
        fills: Node | None = None,
        portfolio: Node | None = None,
        risk: Node | None = None,
        timing: Node | None = None,
    ) -> NodeSet:
        """Attach a Node Set behind ``signal`` with optional component overrides.

        Any unspecified component is filled with a pass-through stub to
        establish contracts. The supplied components are expected to already be
        wired to consume the appropriate upstream (e.g., ``sizing`` should
        consume ``pretrade``).
        """
        # Defaults to pass-through stubs to preserve chain contracts
        pre = pretrade or StubPreTradeGateNode(signal)
        siz = sizing or StubSizingNode(pre)
        exe = execution or StubExecutionNode(siz)
        fil = fills or StubFillIngestNode(exe)
        pf = portfolio or StubPortfolioNode(fil)
        rk = risk or StubRiskControlNode(pf)
        tm = timing or StubTimingGateNode(rk)
        return NodeSet(pretrade=pre, sizing=siz, execution=exe, fills=fil, portfolio=pf, risk=rk, timing=tm)


__all__ = ["NodeSetBuilder", "NodeSet"]
