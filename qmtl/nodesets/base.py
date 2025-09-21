from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from qmtl.sdk.node import Node

from .options import NodeSetOptions, PortfolioScope
from .resources import get_execution_resources
from .stubs import (
    StubPreTradeGateNode,
    StubSizingNode,
    StubExecutionNode,
    StubOrderPublishNode,
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
        scope: Literal["strategy", "world"] | None = None,
        pretrade: Node | None = None,
        sizing: Node | None = None,
        execution: Node | None = None,
        order_publish: Node | None = None,
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
        effective_scope: PortfolioScope = scope or self.options.portfolio_scope
        resources = get_execution_resources(
            world_id,
            portfolio_scope=effective_scope,
            activation_weighting=self.options.activation_weighting,
        )

        def _mark(node: Node) -> Node:
            setattr(node, "world_id", world_id)
            return node

        # Defaults to pass-through stubs to preserve chain contracts
        pre = _mark(pretrade or StubPreTradeGateNode(signal))

        if sizing is None:
            siz_node = StubSizingNode(pre, portfolio=resources.portfolio, weight_fn=resources.weight_fn)
        else:
            siz_node = sizing
            if getattr(siz_node, "portfolio", None) is None:
                setattr(siz_node, "portfolio", resources.portfolio)
            if resources.weight_fn is not None and getattr(siz_node, "weight_fn", None) is None:
                setattr(siz_node, "weight_fn", resources.weight_fn)
        siz = _mark(siz_node)

        exe = _mark(execution or StubExecutionNode(siz))
        pub = _mark(order_publish or StubOrderPublishNode(exe))
        fil = _mark(fills or StubFillIngestNode(pub))

        if portfolio is None:
            pf_node = StubPortfolioNode(fil, portfolio=resources.portfolio)
        else:
            pf_node = portfolio
            if getattr(pf_node, "portfolio", None) is None:
                setattr(pf_node, "portfolio", resources.portfolio)
        pf = _mark(pf_node)

        rk = _mark(risk or StubRiskControlNode(pf))
        tm = _mark(timing or StubTimingGateNode(rk))
        return NodeSet(
            _nodes=(pre, siz, exe, pub, fil, pf, rk, tm),
            name="nodeset",
            modes=("simulate",),
            portfolio_scope=effective_scope,
        )


__all__ = ["NodeSetBuilder", "NodeSet"]
