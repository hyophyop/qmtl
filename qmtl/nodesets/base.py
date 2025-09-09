from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from qmtl.sdk.node import Node

from .options import NodeSetOptions, PortfolioScope
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
    """Opaque grouping of nodes representing an execution subgraph.

    Internals are not exposed; use ``head``, ``tail``, iteration, and metadata
    helpers for inspection.
    """

    _nodes: tuple[Node, ...]
    # Optional metadata for external description/capability queries.
    name: str = "nodeset"
    version: str | None = None
    modes: tuple[str, ...] | None = None  # e.g., ("simulate", "paper", "live")
    portfolio_scope: PortfolioScope | None = None  # "strategy" | "world"
    descriptor: Any | None = None  # Optional adapter descriptor (ports)

    @property
    def head(self) -> Node:
        return self._nodes[0]

    @property
    def tail(self) -> Node:
        return self._nodes[-1]

    @property
    def nodes(self) -> list[Node]:
        return list(self._nodes)

    def __iter__(self):  # type: ignore[override]
        yield from self._nodes

    # ------------------------------------------------------------------
    def describe(self) -> dict:
        """Return a lightweight, stable description of this Node Set."""
        entry = self.head
        exit_ = self.tail
        entry_name = getattr(entry, "name", getattr(entry, "node_id", "entry"))
        exit_name = getattr(exit_, "name", getattr(exit_, "node_id", "exit"))

        ports: dict[str, list[dict[str, Any]]] | None = None
        if self.descriptor is not None and hasattr(self.descriptor, "inputs") and hasattr(self.descriptor, "outputs"):
            def _ps_list(specs):
                out: list[dict[str, Any]] = []
                for s in specs:
                    out.append({
                        "name": getattr(s, "name", None),
                        "required": bool(getattr(s, "required", True)),
                        "description": getattr(s, "description", None),
                    })
                return out

            ports = {
                "inputs": _ps_list(getattr(self.descriptor, "inputs", []) or []),
                "outputs": _ps_list(getattr(self.descriptor, "outputs", []) or []),
            }

        return {
            "name": self.name,
            "version": self.version,
            "entry": entry_name,
            "exit": exit_name,
            "node_count": len(self._nodes),
            "nodes": [getattr(n, "name", getattr(n, "node_id", "node")) for n in self._nodes],
            "ports": ports,
        }

    def capabilities(self) -> dict:
        caps: dict[str, Any] = {}
        if self.modes is not None:
            caps["modes"] = list(self.modes)
        if self.portfolio_scope is not None:
            caps["portfolio_scope"] = self.portfolio_scope
        return caps


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
        return NodeSet(
            _nodes=(pre, siz, exe, fil, pf, rk, tm),
            name="nodeset",
            modes=("simulate",),
            portfolio_scope=scope,
        )


__all__ = ["NodeSetBuilder", "NodeSet"]
