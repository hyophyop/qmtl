from __future__ import annotations

"""CCXT spot Node Set adapter."""

from qmtl.sdk import Node
from qmtl.nodesets.base import NodeSet
from qmtl.nodesets.adapter import NodeSetAdapter, NodeSetDescriptor, PortSpec
from qmtl.nodesets.recipes import make_ccxt_spot_nodeset


class CcxtSpotAdapter(NodeSetAdapter):
    """Adapter exposing a single required input port: 'signal'."""

    descriptor = NodeSetDescriptor(
        name="ccxt_spot",
        inputs=(PortSpec("signal", True, "Trade signal stream"),),
        outputs=(PortSpec("orders", True, "Order stream (execution output)"),),
    )

    def __init__(
        self,
        *,
        exchange_id: str,
        sandbox: bool = False,
        apiKey: str | None = None,
        secret: str | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> None:
        self.exchange_id = exchange_id
        self.sandbox = sandbox
        self.apiKey = apiKey
        self.secret = secret
        self.time_in_force = time_in_force
        self.reduce_only = reduce_only

    def build(self, inputs: dict[str, Node], *, world_id: str, options=None) -> NodeSet:
        self.validate_inputs(inputs)
        signal = inputs["signal"]
        return make_ccxt_spot_nodeset(
            signal,
            world_id,
            exchange_id=self.exchange_id,
            sandbox=self.sandbox,
            apiKey=self.apiKey,
            secret=self.secret,
            time_in_force=self.time_in_force,
            reduce_only=self.reduce_only,
            descriptor=self.descriptor,
        )


__all__ = ["CcxtSpotAdapter"]
