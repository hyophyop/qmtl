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
from qmtl.runtime.sdk.execution_modeling import ExecutionModel
from qmtl.runtime.sdk.order_gate import Activation
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
    compose as compose_steps,
    execution,
    pretrade,
    order_publish,
    fills,
    risk,
    timing,
)
from qmtl.runtime.nodesets.registry import nodeset_recipe
from qmtl.runtime.pipeline.execution_nodes import (
    ExecutionNode as RealExecutionNode,
    OrderPublishNode as RealOrderPublishNode,
    PreTradeGateNode as RealPreTradeNode,
    SizingNode as RealSizingNode,
    PortfolioNode as RealPortfolioNode,
)
from qmtl.runtime.transforms.execution_shared import apply_sizing
from qmtl.runtime.transforms.position_intent import PositionTargetNode, Thresholds
from qmtl.runtime.brokerage import (
    Account,
    BrokerageModel,
    CashBuyingPowerModel,
    ImmediateFillModel,
    NullSlippageModel,
    PercentFeeModel,
)
from qmtl.services.gateway.commit_log import CommitLogWriter


_MISSING = object()


def _seed_execution_resources(
    resources: Any,
    *,
    initial_cash: float,
) -> tuple[Any, Callable[[Mapping[str, Any]], float] | None]:
    """Return portfolio resources after seeding the initial cash balance."""

    portfolio = getattr(resources, "portfolio", None)
    if portfolio is not None and getattr(portfolio, "cash", 0.0) <= 0.0:
        portfolio.cash = float(initial_cash)

    weight_fn = getattr(resources, "weight_fn", None)
    return portfolio, weight_fn


def _build_intent_node(
    upstream: Node,
    *,
    symbol: str,
    thresholds: Thresholds,
    long_weight: float,
    short_weight: float,
    hold_weight: float,
    price_node: Node | None,
    price_resolver: Callable[[CacheView], float | None] | None,
    world_id: str,
) -> PositionTargetNode:
    """Construct and configure the intent node."""

    intent = PositionTargetNode(
        upstream,
        symbol=symbol,
        thresholds=thresholds,
        long_weight=long_weight,
        short_weight=short_weight,
        hold_weight=hold_weight,
        to_order=True,
        price_node=price_node,
        price_resolver=price_resolver,
    )
    setattr(intent, "world_id", world_id)
    return intent


def _create_intent_guard_node(
    intent: PositionTargetNode,
    *,
    portfolio: Any,
    weight_fn: Callable[[Mapping[str, Any]], float] | None,
    world_id: str,
) -> Node:
    """Return a guard node that sizes missing quantities for intents."""

    def _guard_quantity(view: CacheView) -> dict | None:
        data = view[intent][intent.interval]
        if not data:
            return None
        _, payload = data[-1]
        order = dict(payload)
        sized_order: dict | None = order
        if portfolio is not None and "quantity" not in order:
            sized_order = apply_sizing(order, portfolio, weight_fn=weight_fn)
        if sized_order is None:
            return None
        if "quantity" not in sized_order:
            sized_order = dict(sized_order)
            sized_order.setdefault("quantity", 0.0)
        return sized_order

    guard = Node(
        input=intent,
        compute_fn=_guard_quantity,
        name=f"{intent.name}_intent_pretrade_guard",
        interval=intent.interval,
        period=1,
    )
    setattr(guard, "world_id", world_id)
    return guard


def _wrap_pretrade_gate_output(
    gate: Node,
    *,
    intent: PositionTargetNode,
    guard: Node,
) -> Node:
    """Wrap the pre-trade gate output, stripping internal sizing fields."""

    def _strip_quantity(view: CacheView) -> dict | None:
        data = view[gate][gate.interval]
        if not data:
            return None
        _, payload = data[-1]
        order = dict(payload)
        order.pop("quantity", None)
        return order

    stage = Node(
        input=gate,
        compute_fn=_strip_quantity,
        name=f"{gate.name}_sanitized",
        interval=gate.interval,
        period=1,
    )
    setattr(stage, "intent_node", intent)
    setattr(stage, "pretrade_node", gate)
    setattr(stage, "_intent_guard_node", guard)
    return stage


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
        resolved_steps = self._merge_step_overrides(steps or {})
        resolved_steps, legacy_passthrough = self._apply_legacy_components(
            resolved_steps, legacy_components
        )
        attach_kwargs = self._build_attach_kwargs(resolved_steps, legacy_passthrough)

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

    def _merge_step_overrides(
        self,
        overrides: Mapping[str, StepSpec | Callable[[Node], Node] | Node | None],
    ) -> dict[str, StepSpec]:
        resolved_steps = dict(self._steps)
        normalized_overrides = self._normalize_steps(overrides, drop_defaults=False)
        for name, spec in normalized_overrides.items():
            if spec.is_default:
                resolved_steps.pop(name, None)
            else:
                resolved_steps[name] = spec
        return resolved_steps

    def _apply_legacy_components(
        self,
        resolved_steps: Mapping[str, StepSpec],
        legacy_components: Mapping[str, RecipeComponent],
    ) -> tuple[dict[str, StepSpec], dict[str, RecipeComponent]]:
        updated_steps = dict(resolved_steps)
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
                updated_steps.pop(name, None)
                legacy_passthrough.pop(name, None)
            else:
                updated_steps[name] = spec
        return updated_steps, legacy_passthrough

    @staticmethod
    def _build_attach_kwargs(
        resolved_steps: Mapping[str, RecipeComponent],
        legacy_passthrough: Mapping[str, RecipeComponent],
    ) -> dict[str, RecipeComponent]:
        attach_kwargs: dict[str, RecipeComponent] = {}
        for name in STEP_ORDER:
            if name in resolved_steps:
                attach_kwargs[name] = resolved_steps[name]
            elif name in legacy_passthrough:
                attach_kwargs[name] = legacy_passthrough[name]
        return attach_kwargs

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
    name_hint = spec.name or getattr(descriptor_value, "name", None)
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


def _intent_pretrade_factory(
    upstream: Node,
    *,
    symbol: str,
    thresholds: Thresholds,
    long_weight: float,
    short_weight: float,
    hold_weight: float,
    price_node: Node | None,
    price_resolver: Callable[[CacheView], float | None] | None,
    activation_map: Mapping[str, Activation] | None,
    brokerage: BrokerageModel | None,
    account: Account | None,
    resources: Any,
    world_id: str,
    initial_cash: float,
) -> Node:
    portfolio, weight_fn = _seed_execution_resources(resources, initial_cash=initial_cash)

    intent = _build_intent_node(
        upstream,
        symbol=symbol,
        thresholds=thresholds,
        long_weight=long_weight,
        short_weight=short_weight,
        hold_weight=hold_weight,
        price_node=price_node,
        price_resolver=price_resolver,
        world_id=world_id,
    )

    guard = _create_intent_guard_node(
        intent,
        portfolio=portfolio,
        weight_fn=weight_fn,
        world_id=world_id,
    )

    resolved_activation = activation_map or _default_activation(symbol)
    resolved_brokerage = brokerage or _default_brokerage()
    resolved_account = account or Account(cash=float(initial_cash))

    gate = RealPreTradeNode(
        guard,
        activation_map=resolved_activation,
        brokerage=resolved_brokerage,
        account=resolved_account,
    )
    setattr(gate, "world_id", world_id)

    return _wrap_pretrade_gate_output(
        gate,
        intent=intent,
        guard=guard,
    )


INTENT_FIRST_DESCRIPTOR = NodeSetDescriptor(
    name="intent_first",
    inputs=(
        PortSpec("signal", True, "Signal stream driving intent generation"),
        PortSpec("price", True, "Price stream for pricing intents"),
    ),
    outputs=(
        PortSpec("orders", True, "Sized order stream after publishing"),
    ),
)


INTENT_FIRST_ADAPTER_PARAMETERS = (
    AdapterParameter("symbol", annotation=str),
    AdapterParameter(
        "thresholds",
        annotation=Thresholds | Mapping[str, float] | None,
        default=None,
        required=False,
    ),
    AdapterParameter("long_weight", annotation=float, default=1.0, required=False),
    AdapterParameter("short_weight", annotation=float, default=-1.0, required=False),
    AdapterParameter("hold_weight", annotation=float, default=0.0, required=False),
    AdapterParameter(
        "activation_map",
        annotation=Mapping[str, Activation] | None,
        default=None,
        required=False,
    ),
    AdapterParameter(
        "brokerage",
        annotation=BrokerageModel | None,
        default=None,
        required=False,
    ),
    AdapterParameter(
        "account",
        annotation=Account | None,
        default=None,
        required=False,
    ),
    AdapterParameter(
        "execution_model",
        annotation=ExecutionModel | None,
        default=None,
        required=False,
    ),
    AdapterParameter(
        "commit_log_writer",
        annotation=CommitLogWriter | None,
        default=None,
        required=False,
    ),
    AdapterParameter(
        "submit_order",
        annotation=Callable[[Mapping[str, Any]], None] | None,
        default=None,
        required=False,
    ),
    AdapterParameter("initial_cash", annotation=float | None, default=None, required=False),
)


_INTENT_FIRST_RECIPE = NodeSetRecipe(
    name="intent_first",
    modes=("simulate",),
    descriptor=INTENT_FIRST_DESCRIPTOR,
    adapter_parameters=INTENT_FIRST_ADAPTER_PARAMETERS,
)


@nodeset_recipe("intent_first")
def make_intent_first_nodeset(
    signal_node: Node,
    world_id: str,
    *,
    symbol: str,
    price_node: Node | None = None,
    price_resolver: Callable[[CacheView], float | None] | None = None,
    thresholds: Thresholds | Mapping[str, float] | None = None,
    long_weight: float = 1.0,
    short_weight: float = -1.0,
    hold_weight: float = 0.0,
    activation_map: Mapping[str, Activation] | None = None,
    brokerage: BrokerageModel | None = None,
    account: Account | None = None,
    execution_model: ExecutionModel | None = None,
    commit_log_writer: CommitLogWriter | None = None,
    submit_order: Callable[[dict], None] | None = None,
    initial_cash: float | None = None,
    options: NodeSetOptions | None = None,
    descriptor: Any | None = None,
) -> NodeSet:
    if price_node is None and price_resolver is None:
        raise ValueError("price_node or price_resolver is required")

    resolved_thresholds = _coerce_thresholds(thresholds)
    cash_seed = float(initial_cash if initial_cash is not None else 100_000.0)

    step_overrides = {
        "pretrade": StepSpec.from_factory(
            _intent_pretrade_factory,
            kwargs={
                "symbol": symbol,
                "thresholds": resolved_thresholds,
                "long_weight": float(long_weight),
                "short_weight": float(short_weight),
                "hold_weight": float(hold_weight),
                "price_node": price_node,
                "price_resolver": price_resolver,
                "activation_map": activation_map,
                "brokerage": brokerage,
                "account": account,
                "initial_cash": cash_seed,
            },
            inject_resources=True,
            inject_world_id=True,
        ),
        "sizing": StepSpec.from_factory(
            RealSizingNode,
            inject_portfolio=True,
            inject_weight_fn=True,
        ),
        "execution": StepSpec.from_factory(
            RealExecutionNode,
            kwargs={"execution_model": execution_model},
        ),
        "order_publish": StepSpec.from_factory(
            RealOrderPublishNode,
            kwargs={
                "commit_log_writer": commit_log_writer,
                "submit_order": submit_order,
            },
        ),
        "portfolio": StepSpec.from_factory(
            RealPortfolioNode,
            inject_portfolio=True,
        ),
    }

    return _INTENT_FIRST_RECIPE.compose(
        signal_node,
        world_id,
        descriptor=descriptor,
        steps=step_overrides,
        options=options,
    )


def _compose_intent_first_adapter(
    inputs: Mapping[str, Node],
    world_id: str,
    *,
    options: NodeSetOptions | None = None,
    descriptor: Any | None = None,
    **config: Any,
) -> NodeSet:
    signal = inputs["signal"]
    if "price" not in inputs:
        raise KeyError("missing required Node Set input port: price")
    price = inputs["price"]
    return make_intent_first_nodeset(
        signal,
        world_id,
        price_node=price,
        options=options,
        descriptor=descriptor,
        **config,
    )


INTENT_FIRST_ADAPTER_SPEC = RecipeAdapterSpec(
    compose=_compose_intent_first_adapter,
    descriptor=INTENT_FIRST_DESCRIPTOR,
    parameters=_INTENT_FIRST_RECIPE.adapter_parameters,
    name="intent_first",
    class_name="IntentFirstAdapter",
    doc="Adapter exposing 'signal' and 'price' input ports for the intent-first recipe.",
    input_port="signal",
    modes=_INTENT_FIRST_RECIPE.default_modes,
)


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

    return compose_steps(
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
    "INTENT_FIRST_DEFAULT_THRESHOLDS",
    "INTENT_FIRST_DESCRIPTOR",
    "INTENT_FIRST_ADAPTER_PARAMETERS",
    "INTENT_FIRST_ADAPTER_SPEC",
    "make_intent_first_nodeset",
    "CCXT_SPOT_DESCRIPTOR",
    "CCXT_SPOT_ADAPTER_SPEC",
    "make_ccxt_spot_nodeset",
    "make_ccxt_futures_nodeset",
]
INTENT_FIRST_DEFAULT_THRESHOLDS = Thresholds(
    long_enter=0.6,
    short_enter=-0.6,
    long_exit=0.2,
    short_exit=-0.2,
)


def _coerce_thresholds(value: Thresholds | Mapping[str, float] | None) -> Thresholds:
    if value is None:
        return INTENT_FIRST_DEFAULT_THRESHOLDS
    if isinstance(value, Thresholds):
        return value
    if isinstance(value, Mapping):
        return Thresholds(**value)  # type: ignore[arg-type]
    raise TypeError("thresholds must be a Thresholds instance or mapping")


def _default_activation(symbol: str) -> Mapping[str, Activation]:
    return {symbol: Activation(enabled=True)}


def _default_brokerage() -> BrokerageModel:
    return BrokerageModel(
        CashBuyingPowerModel(),
        PercentFeeModel(rate=0.0),
        NullSlippageModel(),
        ImmediateFillModel(),
    )
