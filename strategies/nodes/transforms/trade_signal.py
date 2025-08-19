"""Generate basic trade signals from alpha values."""

from collections.abc import Sequence

from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node

TAGS = {
    "scope": "transform",
    "family": "trade_signal",
    "interval": "1d",
    "asset": "sample",
}


def threshold_signal_node(
    alpha: float,
    *,
    long_threshold: float,
    short_threshold: float,
    size: float = 1.0,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """Return a trade signal based on threshold comparison.

    Parameters
    ----------
    alpha:
        Latest alpha value.
    long_threshold:
        Minimum alpha required to issue a ``BUY`` signal.
    short_threshold:
        Maximum alpha allowed to issue a ``SELL`` signal.
    size:
        Absolute trade size for ``BUY`` or ``SELL`` actions.
    stop_loss:
        Optional stop-loss level to include in the signal.
    take_profit:
        Optional take-profit level to include in the signal.
    """

    if alpha >= long_threshold:
        action = "BUY"
    elif alpha <= short_threshold:
        action = "SELL"
    else:
        action = "HOLD"

    signal = {"action": action, "size": size}
    if stop_loss is not None:
        signal["stop_loss"] = stop_loss
    if take_profit is not None:
        signal["take_profit"] = take_profit
    return signal


def trade_signal_node(
    alpha_history: Sequence[float],
    *,
    long_threshold: float,
    short_threshold: float,
    size: float = 1.0,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """Return a trade signal using the latest value from an alpha history.

    Parameters
    ----------
    alpha_history:
        Sequence of historical alpha values with the most recent last.
    long_threshold:
        Minimum alpha required to issue a ``BUY`` signal.
    short_threshold:
        Maximum alpha allowed to issue a ``SELL`` signal.
    size:
        Absolute trade size for ``BUY`` or ``SELL`` actions.
    stop_loss:
        Optional stop-loss level to include in the signal.
    take_profit:
        Optional take-profit level to include in the signal.
    """

    latest_alpha = alpha_history[-1] if alpha_history else 0.0
    return threshold_signal_node(
        latest_alpha,
        long_threshold=long_threshold,
        short_threshold=short_threshold,
        size=size,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )


class TradeSignalGeneratorNode(Node):
    """Node wrapper generating trade signals from alpha history."""

    def __init__(
        self,
        history: Node,
        *,
        long_threshold: float,
        short_threshold: float,
        size: float = 1.0,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        name: str | None = None,
    ) -> None:
        self.history = history
        self.long_threshold = long_threshold
        self.short_threshold = short_threshold
        self.size = size
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        super().__init__(
            input=history,
            compute_fn=self._compute,
            name=name or f"{history.name}_trade_signal",
            interval=history.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.history][self.history.interval]
        if not data:
            return None
        series = data[-1][1]
        return trade_signal_node(
            series,
            long_threshold=self.long_threshold,
            short_threshold=self.short_threshold,
            size=self.size,
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
        )
