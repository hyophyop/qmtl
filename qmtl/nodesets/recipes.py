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
from qmtl.nodesets.steps import pretrade, sizing, execution, fills, portfolio, risk, timing, compose


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
    def _exec(view: CacheView, upstream: Node) -> dict | None:  # capture client/time_in_force/reduce_only
        # Sized order arrives on `upstream` as provided by the Steps DSL.
        data = view[upstream][upstream.interval]
        if not data:
            return None
        _, order = data[-1]
        order = dict(order)
        order.setdefault("time_in_force", time_in_force)
        if reduce_only:
            order["reduce_only"] = True
        client.post_order(order)
        return order

    # Build the full chain via compose with our parameterized execution step.
    return compose(
        signal_node,
        steps=[
            pretrade(),
            sizing(),
            execution(compute_fn=_exec),
            fills(),
            portfolio(),
            risk(),
            timing(),
        ],
        name="ccxt_spot",
        modes=("simulate", "paper", "live"),
        portfolio_scope="strategy",
        descriptor=descriptor,
    )


__all__ = ["make_ccxt_spot_nodeset"]
