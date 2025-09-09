from __future__ import annotations

"""Built-in Node Set recipes.

Recipe functions return a composed NodeSet and are the preferred public API
for constructing exchange-backed execution pipelines. Treat the returned
NodeSet as a black box; its internal composition may change between versions.
"""

from typing import Any

from qmtl.sdk import Node
from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.brokerage_client import (
    CcxtBrokerageClient,
    FakeBrokerageClient,
)
from qmtl.nodesets.base import NodeSet
from qmtl.pipeline.execution_nodes import SizingNode as RealSizingNode, PortfolioNode as RealPortfolioNode
from qmtl.sdk.portfolio import Portfolio
from qmtl.nodesets.steps import (
    pretrade,
    sizing,
    execution,
    order_publish,
    fills,
    portfolio,
    risk,
    timing,
    compose,
)


_WORLD_PORTFOLIOS: dict[str, Portfolio] = {}


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

    # Build the full chain via compose with our parameterized execution step.
    # Select portfolio instance; world-shared to honor portfolio_scope when used in future extensions
    portfolio_obj = _WORLD_PORTFOLIOS.setdefault(world_id, Portfolio())

    def _sizing_step(upstream: Node) -> Node:
        # Activation-weight soft gating: consult Runner's ActivationManager when available.
        def _weight(order: dict) -> float:
            try:
                from qmtl.sdk.runner import Runner  # late import to avoid cycles

                am = Runner._activation_manager
                if am is None:
                    return 1.0
                qty = float(order.get("quantity", 0.0))
                side = "buy" if qty >= 0 else "sell"
                w = float(am.weight_for_side(side))
                if w < 0.0:
                    return 0.0
                if w > 1.0:
                    return 1.0
                return w
            except Exception:
                return 1.0

        # Use a lightweight local portfolio for sizing helpers; portfolio state may be
        # updated by a downstream PortfolioNode in richer recipes.
        return RealSizingNode(upstream, portfolio=portfolio_obj, weight_fn=_weight)

    def _portfolio_step(upstream: Node) -> Node:
        return RealPortfolioNode(upstream, portfolio=portfolio_obj)

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
        portfolio_scope="strategy",
        descriptor=descriptor,
    )


__all__ = ["make_ccxt_spot_nodeset"]
