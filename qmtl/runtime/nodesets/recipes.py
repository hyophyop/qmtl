from __future__ import annotations

"""Built-in Node Set recipes.

Recipe functions return a composed NodeSet and are the preferred public API
for constructing exchange-backed execution pipelines. Treat the returned
NodeSet as a black box; its internal composition may change between versions.
"""

from dataclasses import dataclass
from inspect import Parameter, Signature
from types import MappingProxyType
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
from qmtl.runtime.nodesets.adapter import NodeSetAdapter, NodeSetDescriptor, PortSpec
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


_MISSING = object()


@dataclass(frozen=True)
class AdapterParameter:
    """Declarative description of an adapter configuration parameter."""

    name: str
    annotation: Any = Any
    default: Any = _MISSING
    required: bool = True
    description: str | None = None

    def has_default(self) -> bool:
        return self.default is not _MISSING


@dataclass(frozen=True)
class RecipeAdapterSpec:
    """Specification describing how to build an adapter from a recipe."""

    compose: Callable[..., NodeSet]
    descriptor: NodeSetDescriptor
    parameters: Sequence[AdapterParameter] = ()
    name: str | None = None
    doc: str | None = None
    input_port: str = "signal"
    class_name: str | None = None
    modes: Sequence[str] | None = None

    def __post_init__(self) -> None:
        if not self.input_port:
            raise ValueError("input_port must be a non-empty string")


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
        adapter_parameters: Sequence[AdapterParameter] | None = None,
    ) -> None:
        template = builder or NodeSetBuilder()
        self.builder = template
        self._builder_template = template
        self._builder_cls = type(template)
        base_options = getattr(template, "options", None)
        self._builder_options = base_options if base_options is not None else NodeSetOptions()
        self.name = name
        self._modes = tuple(modes) if modes is not None else None
        self._descriptor = descriptor
        self._steps = self._normalize_steps(steps or {}, drop_defaults=True)
        self._adapter_parameters = tuple(adapter_parameters or ())

    def compose(
        self,
        signal: Node,
        world_id: str,
        *,
        scope: Literal["strategy", "world"] | None = None,
        descriptor: Any | None = None,
        steps: Mapping[str, StepSpec | Callable[[Node], Node] | Node | None] | None = None,
        options: NodeSetOptions | None = None,
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

        builder = self._make_builder(options)

        return builder.attach(
            signal,
            world_id=world_id,
            scope=scope,
            name=self.name,
            modes=self._modes,
            descriptor=descriptor if descriptor is not None else self._descriptor,
            **attach_kwargs,
        )

    def _make_builder(self, options: NodeSetOptions | None) -> NodeSetBuilder:
        opts = options or self._builder_options
        try:
            return self._builder_cls(options=opts)
        except TypeError:
            if options is None:
                return self._builder_template
            raise

    @property
    def descriptor(self) -> Any | None:
        return self._descriptor

    @property
    def default_modes(self) -> tuple[str, ...] | None:
        return self._modes

    @property
    def adapter_parameters(self) -> tuple[AdapterParameter, ...]:
        return self._adapter_parameters

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


def build_adapter(spec: RecipeAdapterSpec) -> type[NodeSetAdapter]:
    """Return a concrete :class:`NodeSetAdapter` for ``spec``."""

    parameters = tuple(spec.parameters)
    descriptor_value = spec.descriptor
    compose = spec.compose
    input_port = spec.input_port
    name_hint = spec.name or descriptor.name
    class_name = spec.class_name or (
        f"{''.join(part.capitalize() for part in (name_hint or 'nodeset').split('_'))}Adapter"
    )
    doc = spec.doc or f"Adapter generated for recipe '{name_hint}'."
    modes = tuple(spec.modes) if spec.modes is not None else None

    slots = tuple(param.name for param in parameters) + ("_config",)

    class GeneratedAdapter(NodeSetAdapter):
        __slots__ = slots
        descriptor = descriptor_value
        recipe_name = name_hint
        default_modes = modes
        adapter_parameters = parameters
        __doc__ = doc

        def __init__(self, **kwargs: Any) -> None:
            super().__init__()
            values: dict[str, Any] = {}
            for param in parameters:
                if param.name in kwargs:
                    value = kwargs.pop(param.name)
                elif param.has_default():
                    value = param.default
                elif param.required:
                    raise TypeError(f"missing required adapter parameter: {param.name}")
                else:
                    value = None
                setattr(self, param.name, value)
                values[param.name] = value

            if kwargs:
                unexpected = ", ".join(sorted(kwargs))
                raise TypeError(f"unexpected adapter parameter(s): {unexpected}")

            object.__setattr__(self, "_config", MappingProxyType(dict(values)))

        def build(
            self,
            inputs: Mapping[str, Node],
            *,
            world_id: str,
            options: NodeSetOptions | None = None,
        ) -> NodeSet:
            self.validate_inputs(inputs)
            if input_port not in inputs:
                raise KeyError(f"Missing required input port: {input_port}")

            compose_kwargs = {param.name: getattr(self, param.name) for param in parameters}
            return compose(
                inputs,
                world_id,
                options=options,
                descriptor=descriptor_value,
                **compose_kwargs,
            )

        @property
        def config(self) -> Mapping[str, Any]:
            return self._config

    init_parameters = [Parameter("self", Parameter.POSITIONAL_OR_KEYWORD)]
    for param in parameters:
        default = param.default if param.has_default() else Parameter.empty
        annotation = param.annotation if param.annotation is not None else Parameter.empty
        init_parameters.append(
            Parameter(
                param.name,
                kind=Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )
    GeneratedAdapter.__init__.__signature__ = Signature(init_parameters)

    GeneratedAdapter.__name__ = class_name
    GeneratedAdapter.__qualname__ = class_name
    GeneratedAdapter.__module__ = compose.__module__

    return GeneratedAdapter


CCXT_SPOT_DESCRIPTOR = NodeSetDescriptor(
    name="ccxt_spot",
    inputs=(PortSpec("signal", True, "Trade signal stream"),),
    outputs=(PortSpec("orders", True, "Order stream (execution output)"),),
)

CCXT_SPOT_ADAPTER_PARAMETERS = (
    AdapterParameter("exchange_id", annotation=str),
    AdapterParameter("sandbox", annotation=bool, default=False, required=False),
    AdapterParameter("apiKey", annotation=str | None, default=None, required=False),
    AdapterParameter("secret", annotation=str | None, default=None, required=False),
    AdapterParameter("time_in_force", annotation=str, default="GTC", required=False),
    AdapterParameter("reduce_only", annotation=bool, default=False, required=False),
)

_CCXT_SPOT_RECIPE = NodeSetRecipe(
    name="ccxt_spot",
    modes=("simulate", "paper", "live"),
    descriptor=CCXT_SPOT_DESCRIPTOR,
    steps={
        "sizing": StepSpec.from_factory(
            RealSizingNode,
            inject_portfolio=True,
            inject_weight_fn=True,
        ),
        "portfolio": StepSpec.from_factory(
            RealPortfolioNode,
            inject_portfolio=True,
        ),
    },
    adapter_parameters=CCXT_SPOT_ADAPTER_PARAMETERS,
)


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

    def _exec(view: CacheView, upstream: Node) -> dict | None:
        data = view[upstream][upstream.interval]
        if not data:
            return None
        _, order = data[-1]
        order = dict(order)
        order.setdefault("time_in_force", time_in_force)
        if reduce_only:
            order["reduce_only"] = True
        return order

    def _publish(view: CacheView, upstream: Node) -> dict | None:
        data = view[upstream][upstream.interval]
        if not data:
            return None
        _, order = data[-1]
        client.post_order(order)
        return order

    resolved_options = options or NodeSetOptions()
    step_overrides = {
        "execution": StepSpec.from_step(execution(compute_fn=_exec)),
        "order_publish": StepSpec.from_step(order_publish(compute_fn=_publish)),
    }

    return _CCXT_SPOT_RECIPE.compose(
        signal_node,
        world_id,
        descriptor=descriptor,
        steps=step_overrides,
        options=resolved_options,
    )


def _compose_ccxt_spot_adapter(
    inputs: Mapping[str, Node],
    world_id: str,
    *,
    options: NodeSetOptions | None = None,
    descriptor: Any | None = None,
    **config: Any,
) -> NodeSet:
    signal = inputs["signal"]
    return make_ccxt_spot_nodeset(
        signal,
        world_id,
        descriptor=descriptor,
        options=options,
        **config,
    )


CCXT_SPOT_ADAPTER_SPEC = RecipeAdapterSpec(
    compose=_compose_ccxt_spot_adapter,
    descriptor=CCXT_SPOT_DESCRIPTOR,
    parameters=_CCXT_SPOT_RECIPE.adapter_parameters,
    name="ccxt_spot",
    class_name="CcxtSpotAdapter",
    doc="Adapter exposing a single required input port: 'signal'.",
    input_port="signal",
    modes=_CCXT_SPOT_RECIPE.default_modes,
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


__all__ = [
    "AdapterParameter",
    "RecipeAdapterSpec",
    "NodeSetRecipe",
    "build_adapter",
    "CCXT_SPOT_DESCRIPTOR",
    "CCXT_SPOT_ADAPTER_SPEC",
    "make_ccxt_spot_nodeset",
    "make_ccxt_futures_nodeset",
]
