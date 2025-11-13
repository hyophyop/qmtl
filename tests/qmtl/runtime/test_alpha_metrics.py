from __future__ import annotations

from qmtl.runtime.alpha_metrics import (
    ALPHA_PERFORMANCE_METRIC_KEYS,
    default_alpha_performance_metrics,
    parse_alpha_metrics_envelope,
    sanitize_alpha_performance_metrics,
)


def test_default_alpha_metrics_zeroed() -> None:
    defaults = default_alpha_performance_metrics()
    assert set(defaults) == {f"alpha_performance.{k}" for k in ALPHA_PERFORMANCE_METRIC_KEYS}
    assert all(value == 0.0 for value in defaults.values())


def test_sanitize_ignores_unknown_and_nan() -> None:
    raw = {
        "alpha_performance.sharpe": 1.23,
        "alpha_performance.max_drawdown": -0.5,
        "alpha_performance.unknown": 5.0,
        "alpha_performance.win_ratio": float("nan"),
        "other_metric": 0.0,
        123: 2.0,
    }
    cleaned = sanitize_alpha_performance_metrics(raw)
    assert cleaned["alpha_performance.sharpe"] == 1.23
    assert cleaned["alpha_performance.max_drawdown"] == -0.5
    assert cleaned["alpha_performance.win_ratio"] == 0.0
    assert "alpha_performance.unknown" not in cleaned
    assert "other_metric" not in cleaned


def test_parse_envelope_produces_nested_defaults() -> None:
    payload = {
        "per_world": {
            "world-1": {"alpha_performance.sharpe": 0.4},
            "world-2": {"alpha_performance.max_drawdown": -0.2},
        },
        "per_strategy": {
            "s1": {
                "world-1": {"alpha_performance.sharpe": 0.1},
            },
            "s2": {
                "world-2": {"alpha_performance.win_ratio": 0.5},
            },
        },
    }
    per_world, per_strategy = parse_alpha_metrics_envelope(payload)
    assert set(per_world) == {"world-1", "world-2"}
    for metrics in per_world.values():
        assert all(k.startswith("alpha_performance.") for k in metrics)
    assert per_world["world-1"]["alpha_performance.sharpe"] == 0.4
    assert per_strategy["s1"]["world-1"]["alpha_performance.sharpe"] == 0.1
    assert per_strategy["s2"]["world-2"]["alpha_performance.win_ratio"] == 0.5
