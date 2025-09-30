from __future__ import annotations

"""CCXT futures Node Set adapter."""

from qmtl.runtime.sdk import Node
from qmtl.runtime.nodesets.base import NodeSet
from qmtl.runtime.nodesets.adapter import NodeSetAdapter, NodeSetDescriptor, PortSpec
from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.nodesets.recipes import make_ccxt_futures_nodeset


class CcxtFuturesAdapter(NodeSetAdapter):
    """Adapter exposing a single required input port: 'signal'."""

    descriptor = NodeSetDescriptor(
        name="ccxt_futures",
        inputs=(PortSpec("signal", True, "Trade signal stream"),),
        outputs=(PortSpec("orders", True, "Order stream (execution output)"),),
    )

    def __init__(
        self,
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
    ) -> None:
        self.exchange_id = exchange_id
        self.sandbox = sandbox
        self.apiKey = apiKey
        self.secret = secret
        self.time_in_force = time_in_force
        self.reduce_only = reduce_only
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.hedge_mode = hedge_mode

    def build(
        self,
        inputs: dict[str, Node],
        *,
        world_id: str,
        options: NodeSetOptions | None = None,
    ) -> NodeSet:
        self.validate_inputs(inputs)
        signal = inputs["signal"]
        return make_ccxt_futures_nodeset(
            signal,
            world_id,
            exchange_id=self.exchange_id,
            sandbox=self.sandbox,
            apiKey=self.apiKey,
            secret=self.secret,
            time_in_force=self.time_in_force,
            reduce_only=self.reduce_only,
            leverage=self.leverage,
            margin_mode=self.margin_mode,
            hedge_mode=self.hedge_mode,
            options=options,
            descriptor=self.descriptor,
        )


__all__ = ["CcxtFuturesAdapter"]

