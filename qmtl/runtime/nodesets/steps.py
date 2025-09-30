from __future__ import annotations

"""Small Steps DSL for composing Node Sets.

Each step factory returns a callable that takes an upstream Node and returns a
new Node wired to it. The canonical order is:
pretrade → sizing → execution → order_publish → fills → portfolio → risk → timing.

`compose(signal, steps)` applies the provided steps left-to-right and returns a
NodeSet. Missing trailing steps are filled with defaults; extra steps raise.

The module also exposes :class:`StepSpec`, a declarative descriptor used by
recipes to request default fallbacks or resource-aware overrides without
writing ad-hoc wiring lambdas.
"""

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping, Sequence, TYPE_CHECKING

from qmtl.runtime.sdk import Node
from qmtl.runtime.nodesets.stubs import (
    StubPreTradeGateNode,
    StubSizingNode,
    StubExecutionNode,
    StubOrderPublishNode,
    StubFillIngestNode,
    StubPortfolioNode,
    StubRiskControlNode,
    StubTimingGateNode,
)

if TYPE_CHECKING:
    from qmtl.runtime.nodesets.base import NodeSetContext, NodeSet


Step = Callable[[Node], Node]
"""Callable that wires a node behind ``upstream``."""


StepName = Literal[
    "pretrade",
    "sizing",
    "execution",
    "order_publish",
    "fills",
    "portfolio",
    "risk",
    "timing",
]


STEP_ORDER: tuple[StepName, ...] = (
    "pretrade",
    "sizing",
    "execution",
    "order_publish",
    "fills",
    "portfolio",
    "risk",
    "timing",
)


@dataclass(frozen=True)
class StepSpec:
    """Declarative description of a recipe step override."""

    factory: Callable[..., Node] | None = None
    """Callable that returns a node when supplied with ``upstream`` and kwargs."""

    step: Step | None = None
    """Pre-bound step callable (no access to a recipe context)."""

    node: Node | None = None
    """Pre-built node instance."""

    kwargs: Mapping[str, Any] = field(default_factory=dict)
    """Static keyword arguments passed to ``factory`` when invoked."""

    _injections: tuple[tuple[str, Callable[["NodeSetContext"], Any]], ...] = ()
    """Context-aware injections expressed as (argument, resolver) pairs."""

    @classmethod
    def default(cls) -> "StepSpec":
        """Return a spec that defers to the default stub."""

        return cls()

    @classmethod
    def from_step(cls, step: Step) -> "StepSpec":
        """Wrap a pre-built :class:`Step` callable."""

        return cls(step=step)

    @classmethod
    def from_node(cls, node: Node) -> "StepSpec":
        """Wrap an already constructed node."""

        return cls(node=node)

    @classmethod
    def from_factory(
        cls,
        factory: Callable[..., Node],
        *,
        kwargs: Mapping[str, Any] | None = None,
        inject_portfolio: bool = False,
        inject_weight_fn: bool = False,
        inject_resources: bool = False,
        inject_world_id: bool = False,
    ) -> "StepSpec":
        """Create a spec around ``factory`` with optional resource injections."""

        injections: list[tuple[str, Callable[["NodeSetContext"], Any]]] = []
        if inject_portfolio:
            injections.append(("portfolio", lambda ctx: ctx.resources.portfolio))
        if inject_weight_fn:
            injections.append(("weight_fn", lambda ctx: ctx.resources.weight_fn))
        if inject_resources:
            injections.append(("resources", lambda ctx: ctx.resources))
        if inject_world_id:
            injections.append(("world_id", lambda ctx: ctx.world_id))

        return cls(
            factory=factory,
            kwargs=dict(kwargs or {}),
            _injections=tuple(injections),
        )

    @classmethod
    def ensure(
        cls,
        component: "StepSpec | Step | Node | None",
    ) -> "StepSpec":
        """Normalize arbitrary step components to a :class:`StepSpec`."""

        if component is None:
            return cls.default()
        if isinstance(component, StepSpec):
            return component
        if isinstance(component, Node):
            return cls.from_node(component)
        if callable(component):
            try:
                signature = inspect.signature(component)
            except (TypeError, ValueError):
                return cls.from_step(component)
            if len(signature.parameters) == 1:
                return cls.from_step(component)
        if isinstance(component, StepSpec):  # pragma: no cover - handled above but aids mypy
            return component
        raise TypeError(f"Unsupported step component: {type(component)!r}")

    @property
    def is_default(self) -> bool:
        """Return ``True`` when this spec defers to default behaviour."""

        return (
            self.factory is None
            and self.step is None
            and self.node is None
            and not self.kwargs
            and not self._injections
        )

    def with_injection(
        self,
        argument: str,
        resolver: Callable[["NodeSetContext"], Any],
    ) -> "StepSpec":
        """Return a new spec with an additional context-driven injection."""

        return StepSpec(
            factory=self.factory,
            step=self.step,
            node=self.node,
            kwargs=dict(self.kwargs),
            _injections=self._injections + ((argument, resolver),),
        )

    def bind(
        self,
        upstream: Node,
        ctx: "NodeSetContext",
        default_factory: Callable[[Node, "NodeSetContext"], Node],
    ) -> Node:
        """Realize this specification into a concrete node instance."""

        if self.node is not None:
            node = self.node
        elif self.step is not None:
            node = self.step(upstream)
        elif self.factory is not None:
            kwargs = dict(self.kwargs)
            for argument, resolver in self._injections:
                if argument not in kwargs:
                    kwargs[argument] = resolver(ctx)
            node = self.factory(upstream, **kwargs)
        else:
            node = default_factory(upstream, ctx)

        if not isinstance(node, Node):
            raise TypeError("Step specification must resolve to a Node instance")
        return node


def pretrade(*, name: str | None = None) -> Step:
    return lambda upstream: StubPreTradeGateNode(upstream, name=name)


def sizing(*, name: str | None = None) -> Step:
    return lambda upstream: StubSizingNode(upstream, name=name)


def execution(*, compute_fn=None, name: str | None = None) -> Step:
    """Execution step.

    - When `compute_fn` is None, returns a `StubExecutionNode`.
    - Otherwise builds a plain `Node` with the provided `compute_fn`.
    """

    if compute_fn is None:
        return lambda upstream: StubExecutionNode(upstream, name=name)

    def _mk(upstream: Node) -> Node:
        def _bound(view):
            return compute_fn(view, upstream)

        return Node(
            input=upstream,
            compute_fn=_bound,
            name=name or f"{upstream.name}_exec",
            interval=upstream.interval,
            period=1,
        )

    return _mk


def order_publish(*, compute_fn=None, name: str | None = None) -> Step:
    """Order publish step."""

    if compute_fn is None:
        return lambda upstream: StubOrderPublishNode(upstream, name=name)

    def _mk(upstream: Node) -> Node:
        def _bound(view):
            return compute_fn(view, upstream)

        return Node(
            input=upstream,
            compute_fn=_bound,
            name=name or f"{upstream.name}_publish",
            interval=upstream.interval,
            period=1,
        )

    return _mk


def fills(*, name: str | None = None) -> Step:
    return lambda upstream: StubFillIngestNode(upstream, name=name)


def portfolio(*, name: str | None = None) -> Step:
    return lambda upstream: StubPortfolioNode(upstream, name=name)


def risk(*, name: str | None = None) -> Step:
    return lambda upstream: StubRiskControlNode(upstream, name=name)


def timing(*, name: str | None = None) -> Step:
    return lambda upstream: StubTimingGateNode(upstream, name=name)


def compose(
    signal: Node,
    steps: Sequence[Step] | None = None,
    *,
    name: str | None = None,
    modes: Sequence[str] | None = None,
    portfolio_scope: str | None = None,
    descriptor: Any | None = None,
) -> NodeSet:
    """Compose a Node Set behind `signal` using the given steps.

    If `steps` is None or shorter than 8, missing trailing steps are filled with
    defaults in the canonical order. If more than 8 steps are provided, raises.
    """

    from qmtl.runtime.nodesets.base import NodeSet

    default_steps: list[Step] = [
        pretrade(),
        sizing(),
        execution(),
        order_publish(),
        fills(),
        portfolio(),
        risk(),
        timing(),
    ]

    steps = list(steps or [])
    if len(steps) > 8:
        raise ValueError("compose accepts at most 8 steps (pretrade..timing)")

    # Overlay provided steps over defaults by position
    for i, st in enumerate(steps):
        default_steps[i] = st

    # Wire left-to-right
    nodes: list[Node] = []
    upstream = signal
    for st in default_steps:
        node = st(upstream)
        nodes.append(node)
        upstream = node

    return NodeSet(
        _nodes=tuple(nodes),
        name=name or "nodeset",
        modes=tuple(modes) if modes is not None else None,
        portfolio_scope=portfolio_scope,  # type: ignore[arg-type]
        descriptor=descriptor,
    )


__all__ = [
    "Step",
    "StepName",
    "STEP_ORDER",
    "StepSpec",
    "pretrade",
    "sizing",
    "execution",
    "order_publish",
    "fills",
    "portfolio",
    "risk",
    "timing",
    "compose",
]
