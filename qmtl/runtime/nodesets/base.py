from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Sequence

from qmtl.runtime.sdk.node import Node

from .options import NodeSetOptions, PortfolioScope
from .resources import ExecutionResources, get_execution_resources


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


@dataclass(frozen=True)
class NodeSetContext:
    """Context shared with Node Set recipes during composition."""

    world_id: str
    scope: PortfolioScope
    resources: ExecutionResources
    options: NodeSetOptions


RecipeNodeFactory = Callable[[Node, NodeSetContext], Node]


class NodeSetBuilder:
    """Compose a minimal execution chain behind a signal node.

    This initial scaffold wires pass-through stubs to establish contracts and
    integration points. Concrete Node Sets will replace these with real nodes
    and options.
    """

    def __init__(self, *, options: NodeSetOptions | None = None) -> None:
        self.options = options or NodeSetOptions()

    def context(
        self,
        *,
        world_id: str,
        scope: Literal["strategy", "world"] | None = None,
    ) -> NodeSetContext:
        """Return a :class:`NodeSetContext` for ``world_id`` and ``scope``."""

        effective_scope: PortfolioScope = scope or self.options.portfolio_scope
        resources = get_execution_resources(
            world_id,
            portfolio_scope=effective_scope,
            activation_weighting=self.options.activation_weighting,
        )
        return NodeSetContext(
            world_id=world_id,
            scope=effective_scope,
            resources=resources,
            options=self.options,
        )

    def attach(
        self,
        signal: Node,
        *,
        world_id: str,
        scope: Literal["strategy", "world"] | None = None,
        name: str | None = None,
        modes: Sequence[str] | None = None,
        descriptor: Any | None = None,
        pretrade: Node | RecipeNodeFactory | None = None,
        sizing: Node | RecipeNodeFactory | None = None,
        execution: Node | RecipeNodeFactory | None = None,
        order_publish: Node | RecipeNodeFactory | None = None,
        fills: Node | RecipeNodeFactory | None = None,
        portfolio: Node | RecipeNodeFactory | None = None,
        risk: Node | RecipeNodeFactory | None = None,
        timing: Node | RecipeNodeFactory | None = None,
    ) -> NodeSet:
        """Attach a Node Set behind ``signal`` with optional component overrides.

        Any unspecified component is filled with a pass-through stub to
        establish contracts. The supplied components are expected to already be
        wired to consume the appropriate upstream (e.g., ``sizing`` should
        consume ``pretrade``).
        """
        ctx = self.context(world_id=world_id, scope=scope)

        def _resolve(component, upstream, default_factory: RecipeNodeFactory) -> Node:
            # Import locally to avoid circular dependency during module load.
            from .steps import StepSpec

            if isinstance(component, StepSpec):
                node = component.bind(upstream, ctx, default_factory)
            elif isinstance(component, Node):
                node = component
            elif callable(component):
                node = component(upstream, ctx)
            else:
                node = default_factory(upstream, ctx)

            if not isinstance(node, Node):
                raise TypeError("Recipe component must produce a Node instance")
            return node

        def _mark(node: Node) -> Node:
            setattr(node, "world_id", ctx.world_id)
            return node

        def _latest_payload(view: CacheView, upstream: Node) -> dict | None:
            data = view[upstream][upstream.interval]
            if not data:
                return None
            _, payload = data[-1]
            return payload

        def _default_pretrade(upstream: Node, _ctx: NodeSetContext) -> Node:
            return Node(
                input=upstream,
                compute_fn=lambda view: _latest_payload(view, upstream),
                name=f"{upstream.name}_pretrade",
                interval=upstream.interval,
                period=1,
            )

        def _default_sizing(upstream: Node, context: NodeSetContext) -> Node:
            node = Node(
                upstream,
                compute_fn=lambda view: _latest_payload(view, upstream),
                name=f"{upstream.name}_sizing",
                interval=upstream.interval,
                period=1,
            )
            setattr(node, "portfolio", context.resources.portfolio)
            setattr(node, "weight_fn", context.resources.weight_fn)
            return node

        def _default_execution(upstream: Node, _ctx: NodeSetContext) -> Node:
            return Node(
                upstream,
                compute_fn=lambda view: _latest_payload(view, upstream),
                name=f"{upstream.name}_exec",
                interval=upstream.interval,
                period=1,
            )

        def _default_publish(upstream: Node, _ctx: NodeSetContext) -> Node:
            return Node(
                upstream,
                compute_fn=lambda view: _latest_payload(view, upstream),
                name=f"{upstream.name}_publish",
                interval=upstream.interval,
                period=1,
            )

        def _default_fills(upstream: Node, _ctx: NodeSetContext) -> Node:
            return Node(
                upstream,
                compute_fn=lambda view: _latest_payload(view, upstream),
                name=f"{upstream.name}_fills",
                interval=upstream.interval,
                period=1,
            )

        def _default_portfolio(upstream: Node, context: NodeSetContext) -> Node:
            node = Node(
                upstream,
                compute_fn=lambda view: _latest_payload(view, upstream),
                name=f"{upstream.name}_portfolio",
                interval=upstream.interval,
                period=1,
            )
            setattr(node, "portfolio", context.resources.portfolio)
            return node

        def _default_risk(upstream: Node, _ctx: NodeSetContext) -> Node:
            return Node(
                upstream,
                compute_fn=lambda view: _latest_payload(view, upstream),
                name=f"{upstream.name}_risk",
                interval=upstream.interval,
                period=1,
            )

        def _default_timing(upstream: Node, _ctx: NodeSetContext) -> Node:
            return Node(
                upstream,
                compute_fn=lambda view: _latest_payload(view, upstream),
                name=f"{upstream.name}_timing",
                interval=upstream.interval,
                period=1,
            )

        pre = _mark(_resolve(pretrade, signal, _default_pretrade))

        siz_node = _resolve(sizing, pre, _default_sizing)
        if getattr(siz_node, "portfolio", None) is None:
            setattr(siz_node, "portfolio", ctx.resources.portfolio)
        if (
            ctx.resources.weight_fn is not None
            and getattr(siz_node, "weight_fn", None) is None
        ):
            setattr(siz_node, "weight_fn", ctx.resources.weight_fn)
        siz = _mark(siz_node)

        exe = _mark(_resolve(execution, siz, _default_execution))
        pub = _mark(_resolve(order_publish, exe, _default_publish))
        fil = _mark(_resolve(fills, pub, _default_fills))

        pf_node = _resolve(portfolio, fil, _default_portfolio)
        if getattr(pf_node, "portfolio", None) is None:
            setattr(pf_node, "portfolio", ctx.resources.portfolio)
        pf = _mark(pf_node)

        rk = _mark(_resolve(risk, pf, _default_risk))
        tm = _mark(_resolve(timing, rk, _default_timing))
        return NodeSet(
            _nodes=(pre, siz, exe, pub, fil, pf, rk, tm),
            name=name or "nodeset",
            modes=tuple(modes) if modes is not None else ("simulate",),
            portfolio_scope=ctx.scope,
            descriptor=descriptor,
        )


__all__ = ["NodeSetBuilder", "NodeSet", "NodeSetContext", "RecipeNodeFactory"]
