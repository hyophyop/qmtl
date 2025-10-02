from __future__ import annotations

"""Built-in Node Set recipes.

Recipe functions return a composed NodeSet and are the preferred public API
for constructing exchange-backed execution pipelines. Treat the returned
NodeSet as a black box; its internal composition may change between versions.
"""

from typing import Any, Callable, Literal, Mapping, Sequence

from qmtl.runtime.sdk import Node
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.brokerage_client import (
    CcxtBrokerageClient,
    FakeBrokerageClient,
    FuturesCcxtBrokerageClient,
)
from qmtl.runtime.nodesets.base import (
    NodeSet,
    NodeSetBuilder,
    NodeSetContext,
)
from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.nodesets.resources import get_execution_resources
from qmtl.runtime.nodesets.steps import (
    StepSpec,
    STEP_ORDER,
    compose,
    execution,
    pretrade,
    order_publish,
    fills,
    risk,
    timing,
)
from qmtl.runtime.nodesets.registry import nodeset_recipe
from qmtl.runtime.pipeline.execution_nodes import (
    SizingNode as RealSizingNode,
    PortfolioNode as RealPortfolioNode,
)


RecipeComponent = Node | Callable[[Node, NodeSetContext], Node] | StepSpec | None


class NodeSetRecipe:
    """Helper that centralizes Node Set composition boilerplate."""

    def __init__(
        self,
        *,
        name: str,
        builder: NodeSetBuilder | None = None,
        modes: Sequence[str] | None = None,
        descriptor: Any | None = None,
        steps: Mapping[str, StepSpec | Callable[[Node], Node] | Node | None] | None = None,
    ) -> None:
        self.builder = builder or NodeSetBuilder()
        self.name = name
        self._modes = tuple(modes) if modes is not None else None
        self._descriptor = descriptor
        self._steps = self._normalize_steps(steps or {}, drop_defaults=True)

    def compose(
        self,
        signal: Node,
        world_id: str,
        *,
        scope: Literal["strategy", "world"] | None = None,
        descriptor: Any | None = None,
        steps: Mapping[str, StepSpec | Callable[[Node], Node] | Node | None] | None = None,
        **legacy_components: RecipeComponent,
    ) -> NodeSet:
        resolved_steps = dict(self._steps)
        overrides = self._normalize_steps(steps or {}, drop_defaults=False)

        for name, spec in overrides.items():
            if spec.is_default:
                resolved_steps.pop(name, None)
            else:
                resolved_steps[name] = spec

        legacy_passthrough: dict[str, RecipeComponent] = {}
        for name, component in legacy_components.items():
            if name not in STEP_ORDER:
                raise KeyError(f"Unknown step name: {name}")
            if component is None:
                continue
            try:
                spec = StepSpec.ensure(component)
            except TypeError:
                legacy_passthrough[name] = component
                continue
            if spec.is_default:
                resolved_steps.pop(name, None)
                legacy_passthrough.pop(name, None)
            else:
                resolved_steps[name] = spec

        attach_kwargs: dict[str, RecipeComponent] = {}
        for name in STEP_ORDER:
            if name in resolved_steps:
                attach_kwargs[name] = resolved_steps[name]
            elif name in legacy_passthrough:
                attach_kwargs[name] = legacy_passthrough[name]

        return self.builder.attach(
            signal,
            world_id=world_id,
            scope=scope,
            name=self.name,
            modes=self._modes,
            descriptor=descriptor if descriptor is not None else self._descriptor,
            **attach_kwargs,
        )

    @staticmethod
    def _normalize_steps(
        steps: Mapping[str, StepSpec | Callable[[Node], Node] | Node | None],
        *,
        drop_defaults: bool,
    ) -> dict[str, StepSpec]:
        normalized: dict[str, StepSpec] = {}
        for name, component in steps.items():
            if name not in STEP_ORDER:
                raise KeyError(f"Unknown step name: {name}")
            spec = StepSpec.ensure(component)
            if spec.is_default and drop_defaults:
                continue
            normalized[name] = spec
        return normalized


@nodeset_recipe("ccxt_spot")
def make_ccxt_spot_nodeset(
    signal_node: Node,
    world_id: str,
    *,
    exchange_id: str,
    sandbox: bool = False,
    apiKey: str | None = None,
    secret: str | None = None,
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    options: NodeSetOptions | None = None,
    descriptor: Any | None = None,
) -> NodeSet:
    """Compose a minimal CCXT spot execution Node Set behind ``signal_node``.

    In simulate mode (no credentials), a FakeBrokerageClient is used. In
    sandbox mode, credentials are required.
    """
    if sandbox and (not apiKey or not secret):
        raise RuntimeError("sandbox mode requires apiKey and secret")

    client: Any
    if apiKey and secret:
        client = CcxtBrokerageClient(
            exchange_id,
            apiKey=apiKey,
            secret=secret,
            sandbox=sandbox,
            options={"defaultType": "spot"},
        )
    else:
        client = FakeBrokerageClient()

    # Execution with CCXT client; applies default opts inline
    def _exec(view: CacheView, upstream: Node) -> dict | None:  # capture time_in_force/reduce_only
        data = view[upstream][upstream.interval]
        if not data:
            return None
        _, order = data[-1]
        order = dict(order)
        order.setdefault("time_in_force", time_in_force)
        if reduce_only:
            order["reduce_only"] = True
        return order

    def _publish(view: CacheView, upstream: Node) -> dict | None:  # capture client
        data = view[upstream][upstream.interval]
        if not data:
            return None
        _, order = data[-1]
        client.post_order(order)
        return order

    opts = options or NodeSetOptions()
    recipe = NodeSetRecipe(
        name="ccxt_spot",
        builder=NodeSetBuilder(options=opts),
        modes=("simulate", "paper", "live"),
    )

    step_overrides = {
        "sizing": StepSpec.from_factory(
            RealSizingNode,
            inject_portfolio=True,
            inject_weight_fn=True,
        ),
        "execution": StepSpec.from_step(execution(compute_fn=_exec)),
        "order_publish": StepSpec.from_step(order_publish(compute_fn=_publish)),
        "portfolio": StepSpec.from_factory(
            RealPortfolioNode,
            inject_portfolio=True,
        ),
    }

    return recipe.compose(
        signal_node,
        world_id,
        descriptor=descriptor,
        steps=step_overrides,
    )


@nodeset_recipe("ccxt_futures")
def make_ccxt_futures_nodeset(
    signal_node: Node,
    world_id: str,
    *,
    exchange_id: str = "binanceusdm",
    sandbox: bool = False,
    apiKey: str | None = None,
    secret: str | None = None,
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    leverage: int | None = None,
    margin_mode: str = "cross",
    hedge_mode: bool | None = None,
    options: NodeSetOptions | None = None,
    descriptor: Any | None = None,
) -> NodeSet:
    """Compose a CCXT futures (perpetual) execution Node Set behind ``signal_node``."""

    if sandbox and (not apiKey or not secret):
        raise RuntimeError("sandbox mode requires apiKey and secret")

    client: Any
    if apiKey and secret:
        client = FuturesCcxtBrokerageClient(
            exchange_id,
            leverage=leverage,
            margin_mode=margin_mode,
            hedge_mode=hedge_mode,
            sandbox=sandbox,
            apiKey=apiKey,
            secret=secret,
        )
    else:
        client = FakeBrokerageClient()

    def _exec(view: CacheView, upstream: Node) -> dict | None:
        data = view[upstream][upstream.interval]
        if not data:
            return None
        _, order = data[-1]
        order = dict(order)
        order.setdefault("time_in_force", time_in_force)
        if reduce_only:
            order["reduce_only"] = True
        if leverage is not None:
            order.setdefault("leverage", leverage)
        return order

    def _publish(view: CacheView, upstream: Node) -> dict | None:
        data = view[upstream][upstream.interval]
        if not data:
            return None
        _, order = data[-1]
        client.post_order(order)
        return order

    opts = options or NodeSetOptions()
    resources = get_execution_resources(
        world_id,
        portfolio_scope=opts.portfolio_scope,
        activation_weighting=opts.activation_weighting,
    )
    portfolio_obj = resources.portfolio
    weight_fn = resources.weight_fn

    def _sizing_step(upstream: Node) -> Node:
        node = RealSizingNode(upstream, portfolio=portfolio_obj, weight_fn=weight_fn)
        setattr(node, "world_id", world_id)
        return node

    def _portfolio_step(upstream: Node) -> Node:
        node = RealPortfolioNode(upstream, portfolio=portfolio_obj)
        setattr(node, "world_id", world_id)
        return node

    return compose(
        signal_node,
        steps=[
            pretrade(),
            _sizing_step,
            execution(compute_fn=_exec),
            order_publish(compute_fn=_publish),
            fills(),
            _portfolio_step,
            risk(),
            timing(),
        ],
        name="ccxt_futures",
        modes=("simulate", "paper", "live"),
        portfolio_scope=opts.portfolio_scope,
        descriptor=descriptor,
    )


__all__ = ["NodeSetRecipe", "make_ccxt_spot_nodeset", "make_ccxt_futures_nodeset"]
