from __future__ import annotations

"""Small Steps DSL for composing Node Sets.

Each step factory returns a callable that takes an upstream Node and returns a
new Node wired to it. The canonical order is:
pretrade → sizing → execution → fills → portfolio → risk → timing.

`compose(signal, steps)` applies the provided steps left-to-right and returns a
NodeSet. Missing trailing steps are filled with defaults; extra steps raise.
"""

from typing import Any, Callable, Sequence

from qmtl.sdk import Node
from qmtl.nodesets.base import NodeSet
from qmtl.nodesets.stubs import (
    StubPreTradeGateNode,
    StubSizingNode,
    StubExecutionNode,
    StubFillIngestNode,
    StubPortfolioNode,
    StubRiskControlNode,
    StubTimingGateNode,
)


Step = Callable[[Node], Node]


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

    If `steps` is None or shorter than 7, missing trailing steps are filled with
    defaults in the canonical order. If more than 7 steps are provided, raises.
    """

    default_steps: list[Step] = [
        pretrade(),
        sizing(),
        execution(),
        fills(),
        portfolio(),
        risk(),
        timing(),
    ]

    steps = list(steps or [])
    if len(steps) > 7:
        raise ValueError("compose accepts at most 7 steps (pretrade..timing)")

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
    "pretrade",
    "sizing",
    "execution",
    "fills",
    "portfolio",
    "risk",
    "timing",
    "compose",
]
