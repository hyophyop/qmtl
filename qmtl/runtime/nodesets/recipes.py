from __future__ import annotations

"""Built-in Node Set recipes.

Recipe functions return a composed NodeSet and are the preferred public API
for constructing exchange-backed execution pipelines. Treat the returned
NodeSet as a black box; its internal composition may change between versions.
"""

from typing import Any

from qmtl.runtime.sdk import Node
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.brokerage_client import (
    CcxtBrokerageClient,
    FakeBrokerageClient,
    FuturesCcxtBrokerageClient,
)
from qmtl.runtime.nodesets.base import NodeSet
from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.nodesets.resources import get_execution_resources
from qmtl.runtime.pipeline.execution_nodes import SizingNode as RealSizingNode, PortfolioNode as RealPortfolioNode
from qmtl.runtime.nodesets.steps import (
    pretrade,
    execution,
    order_publish,
    fills,
    risk,
    timing,
    compose,
)


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
        name="ccxt_spot",
        modes=("simulate", "paper", "live"),
        portfolio_scope=opts.portfolio_scope,
        descriptor=descriptor,
    )


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


__all__ = ["make_ccxt_spot_nodeset", "make_ccxt_futures_nodeset"]
