"""Credit-Liquidity Amplification transform."""

# Source: docs/alphadocs/ideas/gpt5pro/Credit-Liquidity Amplification Theory.md
# Priority: gpt5pro

from __future__ import annotations

import math
import statistics
from typing import Sequence


def _z(series: Sequence[float]) -> float:
    """Return z-score of the last value in ``series``.

    Returns 0.0 when the sample is too small or has zero variance.
    """

    seq = list(series)
    if len(seq) < 2:
        return 0.0
    stdev = statistics.stdev(seq)
    if stdev == 0.0:
        return 0.0
    mean = statistics.fmean(seq)
    return (seq[-1] - mean) / stdev


def credit_liquidity_amplification(
    ebp: Sequence[float],
    cdx: Sequence[float],
    ccbs: Sequence[float],
    ust_liq: Sequence[float],
    amihud: Sequence[float],
    move: Sequence[float],
    b: Sequence[float] | None = None,
    c: Sequence[float] | None = None,
    alpha: Sequence[float] | None = None,
) -> float:
    """Estimate Credit-Liquidity Amplification probability.

    Parameters
    ----------
    ebp, cdx, ccbs, ust_liq, amihud, move:
        Time series of the respective factors.
    b, c, alpha:
        Optional weight vectors for shock, fragility and logistic parameters.

    Returns
    -------
    float
        Probability in the range [0, 1].
    """

    b1, b2, b3 = (b or (1.0, 1.0, 1.0))
    c1, c2 = (c or (1.0, 1.0))
    a0, a1, a2, a3 = (alpha or (0.0, 1.0, 1.0, 1.0))

    shock = b1 * _z(ebp) + b2 * _z(cdx) + b3 * _z(ccbs)
    fragility = c1 * _z(ust_liq) + c2 * _z(amihud)
    move_z = _z(move)

    val = a0 + a1 * shock + a2 * fragility + a3 * move_z
    return 1.0 / (1.0 + math.exp(-val))
