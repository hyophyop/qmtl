"""Pure equity curve linearity metrics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Dict

__all__ = [
    "equity_linearity_metrics",
    "equity_linearity_metrics_v2",
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
    """Compute straightness ratio in (0, 1], normalized for scale."""
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
    """Return linearity metrics for a cumulative PnL/equity series."""
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
    slope, intercept, r2 = _linreg_y_on_t(y)
    if slope == 0.0 and r2 == 0.0:
        return 0.0, 0.0, 0.0
    t_stat = _ols_t_stat_for_slope(y, slope, intercept)
    return slope, r2, t_stat


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


def _ols_t_stat_for_slope(
    y: Sequence[float],
    slope: float,
    intercept: float,
) -> float:
    n = len(y)
    if n <= 2:
        return 0.0
    ss_res = sum((yi - (intercept + slope * i)) ** 2 for i, yi in enumerate(y))
    if ss_res <= 0.0:
        return 0.0
    s2 = ss_res / (n - 2)
    t_mean = (n - 1) / 2.0
    sxx = sum((i - t_mean) ** 2 for i in range(n))
    if sxx <= 0.0:
        return 0.0
    se_b = math.sqrt(s2 / sxx)
    if se_b == 0.0:
        return 0.0
    return slope / se_b


def _coarse(seq: Sequence[float], k: int) -> Sequence[float]:
    if k <= 1 or len(seq) <= 2 * k:
        return seq
    out = list(seq[::k])
    if out[-1] != seq[-1]:
        out.append(seq[-1])
    return out


@dataclass(frozen=True)
class _LinearityComponents:
    r2_up: float
    spearman_rho: float
    t_slope: float
    t_slope_sig: float
    tvr: float
    tuw: float
    nh_frac: float
    mdd_norm: float
    net_gain: float


class _HarmonicMeanLinearityStrategy:
    """Aggregate linearity components into a single score."""

    def __init__(self, orientation: str) -> None:
        self._orientation = orientation

    def _direction_consistent(self, raw_gain: float) -> bool:
        if self._orientation == "up":
            return raw_gain > 0.0
        if self._orientation == "down":
            return raw_gain < 0.0
        return False

    def score(self, components: _LinearityComponents, raw_gain: float, eps: float) -> float:
        if not self._direction_consistent(raw_gain):
            return 0.0

        rho_pos = max(0.0, components.spearman_rho)
        trend = math.sqrt(_clamp01(components.r2_up) * rho_pos)
        smooth = components.tvr
        persistence = components.nh_frac
        dd_penalty = 1.0 / (1.0 + components.mdd_norm)

        values = [max(eps, _clamp01(v)) for v in (trend, smooth, persistence, dd_penalty)]
        return len(values) / sum(1.0 / v for v in values)


def _prepare_oriented_series(
    pnl: Sequence[float],
    *,
    orientation: str,
    use_log: bool,
) -> list[float]:
    sgn = 1.0 if orientation == "up" else -1.0
    y = [sgn * float(v) for v in pnl]
    if use_log:
        if min(y) > 0.0:
            y = [math.log(v) for v in y]
        else:
            # Keep original series if log-transform is not applicable.
            use_log = False
    return y


def _trend_components(y: Sequence[float]) -> tuple[float, float, float, float]:
    slope, r2, t_stat = _ols_slope_r2_t(y)
    r2_up = r2 if slope > 0.0 else 0.0
    rho = _spearman_rho(y)
    t_slope_sig = _clamp01(abs(t_stat) / 3.0)
    return r2_up, rho, t_stat, t_slope_sig


def _tvr_multi_scale(y: Sequence[float], eps: float, scales: Sequence[int]) -> float:
    tvr_vals = []
    for k in scales:
        s = _coarse(y, int(k))
        if len(s) >= 2:
            tvr_vals.append(_variation_ratio(s, eps))
    if not tvr_vals:
        return 0.0
    return math.prod(tvr_vals) ** (1.0 / len(tvr_vals))


def _persistence_components(y: Sequence[float], eps: float) -> tuple[float, float]:
    tuw = _time_under_water(y, eps)
    nh_frac = 1.0 - tuw
    return tuw, nh_frac


def _normalized_drawdown(y: Sequence[float], net_gain: float, eps: float) -> float:
    mdd = _max_drawdown(y)
    return mdd / (abs(net_gain) + eps)


_V2_METRIC_KEYS: tuple[str, ...] = (
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
)


def _empty_v2_metrics() -> Dict[str, float]:
    return {key: 0.0 for key in _V2_METRIC_KEYS}


def equity_linearity_metrics_v2(
    pnl: Sequence[float],
    *,
    orientation: str = "up",  # "up" or "down"
    eps: float = 1e-10,
    use_log: bool = False,
    scales: Sequence[int] = (1, 5, 20),
) -> Dict[str, float]:
    """Robust upward linearity score with multiple corroborating components."""
    y_raw = [float(v) for v in pnl]
    if len(y_raw) < 3:
        return _empty_v2_metrics()

    y = _prepare_oriented_series(y_raw, orientation=orientation, use_log=use_log)
    net_gain = y[-1] - y[0]

    r2_up, rho, t_stat, t_slope_sig = _trend_components(y)
    tvr = _tvr_multi_scale(y, eps, scales)
    tuw, nh_frac = _persistence_components(y, eps)
    mdd_norm = _normalized_drawdown(y, net_gain, eps)

    strategy = _HarmonicMeanLinearityStrategy(orientation=orientation)
    components = _LinearityComponents(
        r2_up=r2_up,
        spearman_rho=rho,
        t_slope=t_stat,
        t_slope_sig=t_slope_sig,
        tvr=tvr,
        tuw=tuw,
        nh_frac=nh_frac,
        mdd_norm=mdd_norm,
        net_gain=net_gain,
    )
    raw_gain = y_raw[-1] - y_raw[0]
    score = strategy.score(components, raw_gain=raw_gain, eps=eps)

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
