import pytest

from qmtl.runtime.indicators import obi_regime_node
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import SourceNode


def _build_view(source: SourceNode, samples):
    data = {source.node_id: {source.interval: list(samples)}}
    return CacheView(data)


def test_obi_regime_state_machine_metrics():
    source = SourceNode(interval="1s", period=16)
    node = obi_regime_node(source, window=10, ema_span=None)

    history = [
        (0, 0.0),
        (1000, 0.35),
        (2000, 0.28),
        (3000, -0.1),
        (4000, -0.35),
        (5000, -0.28),
        (6000, 0.32),
        (7000, 0.31),
    ]

    result = node.compute_fn(_build_view(source, history))
    assert result is not None
    assert result["state"] == "positive"
    assert result["dwell_ms"] == 1000
    assert result["transitions_per_min"] == pytest.approx(34.2857, rel=1e-3)


def test_obi_regime_classifies_trend_and_mean_revert():
    source = SourceNode(interval="1s", period=120)

    trending = obi_regime_node(source, window=60, hi=0.25, lo=-0.25, ema_span=5)
    trending_history = [(i * 5000, 0.32) for i in range(8)]
    trending_result = trending.compute_fn(_build_view(source, trending_history))
    assert trending_result is not None
    assert trending_result["regime"] == "trend"
    assert trending_result["score"] > 0

    mean_revert = obi_regime_node(source, window=20, hi=0.15, lo=-0.15)
    mean_revert_history = []
    for idx in range(20):
        ts = idx * 1000
        value = 0.18 if idx % 2 == 0 else -0.18
        mean_revert_history.append((ts, value))

    mean_revert_result = mean_revert.compute_fn(
        _build_view(source, mean_revert_history)
    )
    assert mean_revert_result is not None
    assert mean_revert_result["regime"] == "mean_revert"
    assert mean_revert_result["score"] < 0
