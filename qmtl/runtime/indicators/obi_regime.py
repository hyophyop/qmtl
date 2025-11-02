"""Order-book imbalance regime detector."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import stdev
from typing import Iterable, List, Tuple

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

__all__ = ["obi_regime_node"]


_POSITIVE = "positive"
_NEGATIVE = "negative"
_NEUTRAL = "neutral"


@dataclass(frozen=True)
class _StateConfig:
    hi: float
    lo: float
    hysteresis: float

    @property
    def upper_exit(self) -> float:
        return self.hi - self.hysteresis

    @property
    def lower_exit(self) -> float:
        return self.lo + self.hysteresis


def _validate_params(hi: float, lo: float, hysteresis: float, window: float) -> None:
    if hi <= lo:
        raise ValueError("'hi' must be greater than 'lo'")
    if hysteresis < 0:
        raise ValueError("'hysteresis' must be non-negative")
    if window <= 0:
        raise ValueError("'window' must be positive")


def _smooth(values: Iterable[float], span: float | None) -> List[float]:
    seq = list(values)
    if span is None or span <= 1:
        return seq
    alpha = 2 / (span + 1)
    smoothed: list[float] = []
    ema_value = 0.0
    for idx, value in enumerate(seq):
        if idx == 0:
            ema_value = value
        else:
            ema_value = alpha * value + (1 - alpha) * ema_value
        smoothed.append(ema_value)
    return smoothed


def _initial_state(config: _StateConfig, value: float) -> str:
    if value >= config.hi:
        return _POSITIVE
    if value <= config.lo:
        return _NEGATIVE
    return _NEUTRAL


def _next_state(config: _StateConfig, previous: str, value: float) -> str:
    if previous == _POSITIVE:
        if value <= config.lo:
            return _NEGATIVE
        if value < config.upper_exit:
            return _NEUTRAL
        return _POSITIVE
    if previous == _NEGATIVE:
        if value >= config.hi:
            return _POSITIVE
        if value > config.lower_exit:
            return _NEUTRAL
        return _NEGATIVE
    # Neutral state
    if value >= config.hi:
        return _POSITIVE
    if value <= config.lo:
        return _NEGATIVE
    return _NEUTRAL


def _select_window(series: Iterable[Tuple[int, float]], window_ms: int) -> List[Tuple[int, float]]:
    windowed: list[tuple[int, float]] = []
    latest_ts: int | None = None
    for ts, value in series:
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts
        windowed.append((ts, value))
    if latest_ts is None:
        return []
    start_ts = latest_ts - window_ms
    return [(ts, value) for ts, value in windowed if ts >= start_ts]


def obi_regime_node(
    obi: Node,
    *,
    hi: float = 0.3,
    lo: float = -0.3,
    hysteresis: float = 0.05,
    window: float = 300,
    ema_span: float | None = None,
    name: str | None = None,
) -> Node:
    """Return a node that classifies OBI regimes using a hysteresis state machine.

    Parameters
    ----------
    obi:
        Node emitting raw or resampled order-book imbalance values.
    hi / lo:
        Thresholds for the positive and negative states respectively. Values
        above ``hi`` enter the positive state, while values below ``lo`` enter
        the negative state.
    hysteresis:
        Buffer applied around the thresholds to suppress rapid oscillations.
        The positive state is maintained until the value falls below
        ``hi - hysteresis`` and the negative state persists until the value
        rises above ``lo + hysteresis``.
    window:
        Rolling lookback horizon in seconds used to aggregate dwell time and
        transition statistics.
    ema_span:
        Optional exponential smoothing span applied before the regime logic.
        Set to ``None`` (default) to disable smoothing.
    name:
        Optional custom name for the resulting node.
    """

    _validate_params(hi, lo, hysteresis, window)
    config = _StateConfig(hi=hi, lo=lo, hysteresis=hysteresis)

    def compute(view: CacheView):
        series_view = view[obi][obi.interval]
        raw_history: list[tuple[int, float]] = []
        for entry in series_view:
            ts, value = entry
            if value is None:
                continue
            try:
                ts_int = int(ts)
                val_float = float(value)
            except (TypeError, ValueError):
                continue
            raw_history.append((ts_int, val_float))

        if not raw_history:
            return None

        window_ms = int(window * 1000)
        if window_ms <= 0:
            window_ms = 1

        history = _select_window(raw_history, window_ms)
        if not history:
            return None

        timestamps = [ts for ts, _ in history]
        values = [value for _, value in history]
        smoothed_values = _smooth(values, ema_span)

        states: list[tuple[int, str]] = []
        previous_state: str | None = None
        for ts, value in zip(timestamps, smoothed_values):
            if previous_state is None:
                state = _initial_state(config, value)
            else:
                state = _next_state(config, previous_state, value)
            states.append((ts, state))
            previous_state = state

        if not states:
            return None

        latest_ts, current_state = states[-1]
        transitions = 0
        for (_, prev_state), (_, next_state) in zip(states, states[1:]):
            if prev_state != next_state:
                transitions += 1

        last_change_ts = latest_ts
        for ts, state in reversed(states):
            if state != current_state:
                break
            last_change_ts = ts
        dwell_ms = max(0, latest_ts - last_change_ts)

        span_ms = max(latest_ts - history[0][0], 1)
        effective_span_ms = min(window_ms, span_ms)
        window_minutes = effective_span_ms / 60000
        if window_minutes <= 0:
            window_minutes = 1e-6
        transitions_per_min = transitions / window_minutes

        abs_mean = sum(abs(v) for v in smoothed_values) / len(smoothed_values)
        volatility = stdev(smoothed_values) if len(smoothed_values) >= 2 else 0.0
        ref = max(abs(hi), abs(lo), 1e-9)
        abs_norm = abs_mean / ref
        mean_revert_component = transitions_per_min / (max(abs_norm, 0.05) * 10)
        volatility_component = volatility / (ref * 4)
        score = abs_norm - mean_revert_component - volatility_component
        score = max(min(score, 1.0), -1.0)

        if score > 0.2:
            regime = "trend"
        elif score < -0.2:
            regime = "mean_revert"
        else:
            regime = "neutral"

        return {
            "state": current_state,
            "dwell_ms": dwell_ms,
            "transitions_per_min": transitions_per_min,
            "regime": regime,
            "score": score,
        }

    return Node(
        input=obi,
        compute_fn=compute,
        name=name or "obi_regime",
        interval=obi.interval,
        period=obi.period,
    )

