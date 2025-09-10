"""Equity curve linearity metrics.

This module computes how "straight" and consistently upward a cumulative PnL
or equity series progresses. It is useful for world-service gating to assess
whether an aggregated portfolio (selected strategies) produces a clean, steady
equity line even if individual constituents are choppier.

The core function, :func:`equity_linearity_metrics`, returns a small set of
interpretable measures and a composite score in [0, 1].

Definitions
-----------
- r2_up: R^2 of a linear fit to the equity curve vs. time. Zeroed if the
  fitted slope is non-positive.
- straightness_ratio: Ratio of the straight-line length to the actual path
  length after normalizing both axes; 1.0 is a perfectly straight path.
- monotonicity: Fraction of non-negative step changes (dy >= 0).
- new_high_frac: Fraction of timestamps that set a new equity high.
- score: A convex combination of the above that rewards smooth, upward paths.

Notes
-----
All metrics are pure functions with no side effects and make no assumptions
about sampling frequency. If the equity series is flat or has <= 2 points,
the result is zeros.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Dict
import math

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView

__all__ = [
    "equity_linearity_metrics",
    "equity_linearity_from_history_node",
    "equity_linearity_metrics_v2",
    "equity_linearity_v2_from_history_node",
]


def _linreg_y_on_t(y: Sequence[float]) -> tuple[float, float, float]:
    """Return slope, intercept, and R^2 for y ~ a + b t, t = 0..n-1.

    If variance is zero or n < 2, returns (0, y0, 0).
    """
    n = len(y)
    if n < 2:
        return 0.0, float(y[0]) if n else 0.0, 0.0
    t_sum = (n - 1) * n / 2.0
    t2_sum = (n - 1) * n * (2 * n - 1) / 6.0
    y_sum = float(sum(y))
    ty_sum = float(sum(i * yi for i, yi in enumerate(y)))

    denom = n * t2_sum - t_sum * t_sum
    if denom == 0:
        return 0.0, float(y[0]), 0.0

    b = (n * ty_sum - t_sum * y_sum) / denom
    a = (y_sum - b * t_sum) / n

    # R^2
    y_mean = y_sum / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    if ss_tot == 0:
        return b, a, 0.0
    ss_res = sum((yi - (a + b * i)) ** 2 for i, yi in enumerate(y))
    r2 = 1.0 - (ss_res / ss_tot)
    # Numerical guard
    r2 = max(0.0, min(1.0, r2))
    return b, a, r2


def _straightness_ratio(y: Sequence[float]) -> float:
    """Compute straightness ratio in (0, 1], normalized for scale.

    The series is normalized so that x spans [0,1] and y spans [0,1] in
    absolute terms (using |Δy|). The straight-line length is sqrt(2) and the
    actual path length accumulates per-step Euclidean distances in this
    normalized space. 1.0 means perfectly straight.
    """
    n = len(y)
    if n < 2:
        return 0.0
    dy_tot = y[-1] - y[0]
    dy_norm = abs(dy_tot)
    if dy_norm == 0:
        # Flat series – no upward linearity
        return 0.0
    x_step = 1.0 / (n - 1)
    inv_dy = 1.0 / dy_norm
    path = 0.0
    for i in range(1, n):
        dy = (y[i] - y[i - 1]) * inv_dy
        step = math.hypot(x_step, dy)
        path += step
    straight = math.sqrt(2.0)
    return max(0.0, min(1.0, straight / path))


def equity_linearity_metrics(pnl: Sequence[float], *, eps: float = 1e-12) -> Dict[str, float]:
    """Return linearity metrics for a cumulative PnL/equity series.

    Parameters
    ----------
    pnl:
        Sequence of cumulative PnL or equity values ordered in time.

    Returns
    -------
    dict
        Keys: ``r2_up``, ``straightness_ratio``, ``monotonicity``,
        ``new_high_frac``, ``net_gain``, ``score`` (0..1).
    """
    y = list(pnl)
    n = len(y)
    if n < 2:
        return {
            "r2_up": 0.0,
            "straightness_ratio": 0.0,
            "monotonicity": 0.0,
            "new_high_frac": 0.0,
            "net_gain": 0.0,
            "score": 0.0,
        }

    net_gain = float(y[-1] - y[0])

    # R^2 with non-negative slope requirement
    slope, _, r2 = _linreg_y_on_t(y)
    r2_up = r2 if slope > 0 else 0.0

    # Straightness in normalized space
    sr = _straightness_ratio(y)

    # Monotonicity and new-high fraction
    inc = [y[i] - y[i - 1] for i in range(1, n)]
    nonneg_steps = sum(1 for d in inc if d > eps)
    monotonicity = nonneg_steps / (n - 1)

    new_highs = 0
    peak = -float("inf")
    for val in y:
        if val > peak + eps:
            new_highs += 1
            peak = val
    new_high_frac = new_highs / n

    # Composite score: emphasize r2_up and straightness; include consistency
    # via monotonicity and new_high_frac. Zero out if net gain is non-positive.
    if net_gain <= 0:
        score = 0.0
    else:
        score = (
            0.45 * r2_up
            + 0.45 * sr
            + 0.10 * ((monotonicity + new_high_frac) / 2.0)
        )

    # Clamp for numerical safety
    score = max(0.0, min(1.0, score))

    return {
        "r2_up": r2_up,
        "straightness_ratio": sr,
        "monotonicity": monotonicity,
        "new_high_frac": new_high_frac,
        "net_gain": net_gain,
        "score": score,
    }


def equity_linearity_from_history_node(history: Node, *, name: str | None = None, eps: float = 1e-12) -> Node:
    """Wrap :func:`equity_linearity_metrics` for a history-producing node.

    The ``history`` node should yield a sequence representing a cumulative PnL
    (or equity) series. If it yields periodic returns instead, upstream should
    convert to cumulative values before feeding this node for best fidelity.
    """

    def compute(view: CacheView):
        data = view[history][history.interval]
        if not data:
            return None
        series = data[-1][1]
        return equity_linearity_metrics(series, eps=eps)

    return Node(
        input=history,
        compute_fn=compute,
        name=name or f"{history.name}_equity_linearity",
        interval=history.interval,
        period=history.period,
    )

# ---------------------------------------------------------------------------
# v2 — robust linearity metric (TVR, Spearman, slope t-stat, TUW, penalties)

def _clamp01(x: float) -> float:
    return 0.0 if x <= 0.0 else 1.0 if x >= 1.0 else x


def _spearman_rho(y: Sequence[float]) -> float:
    n = len(y)
    if n < 3:
        return 0.0

    def rankdata(a: Sequence[float]) -> list[float]:
        idx = sorted(range(n), key=lambda i: a[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            v = a[idx[i]]
            while j + 1 < n and a[idx[j + 1]] == v:
                j += 1
            rank = (i + j + 2) / 2.0  # average rank, 1-based
            for k in range(i, j + 1):
                r[idx[k]] = rank
            i = j + 1
        return r

    rt = rankdata(list(range(n)))
    ry = rankdata(y)
    mt = sum(rt) / n
    my = sum(ry) / n
    num = sum((rt[i] - mt) * (ry[i] - my) for i in range(n))
    den_t = math.sqrt(sum((rt[i] - mt) ** 2 for i in range(n)))
    den_y = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    if den_t == 0.0 or den_y == 0.0:
        return 0.0
    return max(-1.0, min(1.0, num / (den_t * den_y)))


def _ols_slope_r2_t(y: Sequence[float]) -> tuple[float, float, float]:
    n = len(y)
    if n < 3:
        return 0.0, 0.0, 0.0
    t_sum = (n - 1) * n / 2.0
    t2_sum = (n - 1) * n * (2 * n - 1) / 6.0
    y_sum = float(sum(y))
    ty_sum = float(sum(i * yi for i, yi in enumerate(y)))
    denom = n * t2_sum - t_sum * t_sum
    if denom == 0:
        return 0.0, 0.0, 0.0
    b = (n * ty_sum - t_sum * y_sum) / denom
    a = (y_sum - b * t_sum) / n
    y_mean = y_sum / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - (a + b * i)) ** 2 for i, yi in enumerate(y))
    r2 = 0.0 if ss_tot == 0 else max(0.0, min(1.0, 1.0 - ss_res / ss_tot))
    if n <= 2:
        t_stat = 0.0
    else:
        s2 = ss_res / (n - 2)
        sxx = n * t2_sum - t_sum * t_sum
        se_b = math.sqrt(s2 * n / sxx) if sxx > 0 and s2 >= 0 else 0.0
        t_stat = 0.0 if se_b == 0.0 else b / se_b
    return b, r2, t_stat


def _variation_ratio(y: Sequence[float], eps: float) -> float:
    n = len(y)
    if n < 2:
        return 0.0
    inc = [y[i] - y[i - 1] for i in range(1, n)]
    tv = sum(abs(d) for d in inc)
    net = abs(y[-1] - y[0])
    if tv <= eps:
        return 0.0
    return _clamp01(net / tv)


def _time_under_water(y: Sequence[float], eps: float) -> float:
    if not y:
        return 1.0
    peak = -float("inf")
    uw = 0
    for v in y:
        if v > peak + eps:
            peak = v
        else:
            uw += 1
    return uw / len(y)


def _max_drawdown(y: Sequence[float]) -> float:
    peak = -float("inf")
    mdd = 0.0
    for v in y:
        if v > peak:
            peak = v
        else:
            draw = peak - v
            if draw > mdd:
                mdd = draw
    return mdd


def equity_linearity_metrics_v2(
    pnl: Sequence[float],
    *,
    orientation: str = "up",  # "up" or "down"
    eps: float = 1e-10,
    use_log: bool = False,
    scales: Sequence[int] = (1, 5, 20),
) -> Dict[str, float]:
    """Robust upward linearity score with multiple corroborating components.

    Returns keys: r2_up, spearman_rho, t_slope, t_slope_sig, tvr, tuw, nh_frac,
    mdd_norm, net_gain, score (0..1).
    """
    y_raw = [float(v) for v in pnl]
    n = len(y_raw)
    if n < 3:
        return {k: 0.0 for k in (
            "r2_up",
            "spearman_rho",
            "t_slope",
            "t_slope_sig",
            "tvr",
            "tuw",
            "nh_frac",
            "mdd_norm",
            "net_gain",
            "score",
        )}

    sgn = 1.0 if orientation == "up" else -1.0
    y = [sgn * v for v in y_raw]

    if use_log:
        if min(y) > 0.0:
            y = [math.log(v) for v in y]
        else:
            use_log = False

    net_gain = y[-1] - y[0]

    slope, r2, t_stat = _ols_slope_r2_t(y)
    r2_up = r2 if slope > 0 else 0.0
    rho = _spearman_rho(y)
    rho_pos = max(0.0, rho)

    def _coarse(seq: Sequence[float], k: int) -> Sequence[float]:
        if k <= 1 or len(seq) <= 2 * k:
            return seq
        out = seq[::k]
        if out[-1] != seq[-1]:
            out = list(out) + [seq[-1]]
        return out

    tvr_vals = []
    for k in scales:
        s = _coarse(y, int(k))
        if len(s) >= 2:
            tvr_vals.append(_variation_ratio(s, eps))
    tvr = 0.0 if not tvr_vals else math.prod(tvr_vals) ** (1.0 / len(tvr_vals))

    tuw = _time_under_water(y, eps)
    nh_frac = 1.0 - tuw

    mdd = _max_drawdown(y)
    mdd_norm = mdd / (abs(net_gain) + eps)

    trend = math.sqrt(_clamp01(r2_up) * rho_pos)  # geometric mean
    smooth = tvr
    persistence = nh_frac
    dd_penalty = 1.0 / (1.0 + mdd_norm)

    comps = [max(eps, _clamp01(v)) for v in (trend, smooth, persistence, dd_penalty)]
    score = 0.0
    # Directional gate based on raw (pre-transformation) gain
    raw_gain = y_raw[-1] - y_raw[0]
    if (orientation == "up" and raw_gain > 0) or (orientation == "down" and raw_gain < 0):
        score = len(comps) / sum(1.0 / v for v in comps)

    t_slope_sig = _clamp01(abs(t_stat) / 3.0)

    return {
        "r2_up": r2_up,
        "spearman_rho": rho,
        "t_slope": t_stat,
        "t_slope_sig": t_slope_sig,
        "tvr": tvr,
        "tuw": tuw,
        "nh_frac": nh_frac,
        "mdd_norm": mdd_norm,
        "net_gain": net_gain,
        "score": _clamp01(score),
    }


def equity_linearity_v2_from_history_node(
    history: Node,
    *,
    name: str | None = None,
    orientation: str = "up",
    eps: float = 1e-10,
    use_log: bool = False,
    scales: Sequence[int] = (1, 5, 20),
) -> Node:
    """Node wrapper for :func:`equity_linearity_metrics_v2`."""

    def compute(view: CacheView):
        data = view[history][history.interval]
        if not data:
            return None
        series = data[-1][1]
        return equity_linearity_metrics_v2(
            series,
            orientation=orientation,
            eps=eps,
            use_log=use_log,
            scales=scales,
        )

    return Node(
        input=history,
        compute_fn=compute,
        name=name or f"{history.name}_equity_linearity_v2",
        interval=history.interval,
        period=history.period,
    )
