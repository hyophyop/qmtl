"""Simple CCXT spot exchange Node Set builder."""

from __future__ import annotations

from typing import Any, List

from qmtl.sdk import Node
from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.brokerage_client import (
    CcxtBrokerageClient,
    FakeBrokerageClient,
)
from qmtl.transforms import TradeOrderPublisherNode


class CcxtSpotNodeSet:
    """Wire a minimal trade pipeline for CCXT spot exchanges.

    This builder converts a trade signal ``Node`` into an order publisher and
    execution node backed by :class:`CcxtBrokerageClient`. When API credentials
    are omitted, a :class:`FakeBrokerageClient` is used so strategies can run in
    simulate mode without hitting an exchange.

    Parameters
    ----------
    signal_node:
        Upstream ``Node`` emitting trade signals with ``action`` and ``size``.
    world_id:
        Identifier for the trading world. Currently informational.
    exchange_id:
        CCXT exchange id, e.g., ``"binance"``.
    sandbox:
        When ``True``, route to the exchange's sandbox/testnet endpoints. API
        credentials are required in this mode.
    apiKey, secret:
        Credentials passed to :class:`CcxtBrokerageClient`.
    time_in_force:
        Default time in force applied when the signal does not specify one.
    reduce_only:
        If ``True``, tag orders with ``reduce_only`` where supported.
    """

    @staticmethod
    def attach(
        signal_node: Node,
        world_id: str,
        *,
        exchange_id: str,
        sandbox: bool = False,
        apiKey: str | None = None,
        secret: str | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> List[Node]:
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

        publisher = TradeOrderPublisherNode(signal_node)

        def _apply_opts(view: CacheView) -> dict | None:
            data = view[publisher][publisher.interval]
            if not data:
                return None
            _, order = data[-1]
            order = dict(order)
            order.setdefault("time_in_force", time_in_force)
            if reduce_only:
                order["reduce_only"] = True
            return order

        opts_node = Node(
            input=publisher,
            compute_fn=_apply_opts,
            name=f"{publisher.name}_opts",
            interval=publisher.interval,
            period=1,
        )

        def _execute(view: CacheView) -> dict | None:
            data = view[opts_node][opts_node.interval]
            if not data:
                return None
            _, order = data[-1]
            client.post_order(order)
            return order

        exec_node = Node(
            input=opts_node,
            compute_fn=_execute,
            name=f"{opts_node.name}_exec",
            interval=opts_node.interval,
            period=1,
        )

        return [publisher, opts_node, exec_node]
