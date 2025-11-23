from qmtl.services.worldservice.policy_engine import (
    CorrelationRule,
    HysteresisRule,
    Policy,
    ThresholdRule,
    TopKRule,
    evaluate_policy,
    parse_policy,
)


def test_threshold_filtering():
    policy = Policy(thresholds={"sharpe": ThresholdRule(metric="sharpe", min=0.5)})
    metrics = {"s1": {"sharpe": 0.6}, "s2": {"sharpe": 0.4}}
    assert evaluate_policy(metrics, policy) == ["s1"]


def test_topk_selection():
    policy = Policy(top_k=TopKRule(metric="sharpe", k=2))
    metrics = {
        "s1": {"sharpe": 1.0},
        "s2": {"sharpe": 0.8},
        "s3": {"sharpe": 1.5},
    }
    assert evaluate_policy(metrics, policy) == ["s3", "s1"]


def test_topk_missing_metrics_sorted_last():
    policy = Policy(top_k=TopKRule(metric="sharpe", k=2))
    metrics = {
        "s1": {"sharpe": 1.0},
        "s2": {},
        "s3": {"sharpe": 0.4},
    }

    assert evaluate_policy(metrics, policy) == ["s1", "s3"]


def test_threshold_missing_metric_excludes_strategy():
    policy = Policy(
        thresholds={
            "sharpe": ThresholdRule(metric="sharpe", min=0.5),
            "drawdown": ThresholdRule(metric="drawdown", max=0.1),
        }
    )
    metrics = {
        "s1": {"sharpe": 0.6, "drawdown": 0.05},
        "s2": {"sharpe": 0.7},
    }

    assert evaluate_policy(metrics, policy) == ["s1"]


def test_correlation_rule_filters_highly_correlated_candidates():
    policy = Policy(correlation=CorrelationRule(max=0.5))
    metrics = {
        "s1": {"alpha": 0.1},
        "s2": {"alpha": 0.2},
        "s3": {"alpha": 0.3},
    }
    correlations = {
        ("s1", "s2"): 0.8,
        ("s2", "s3"): 0.4,
    }

    assert evaluate_policy(metrics, policy, correlations=correlations) == ["s1", "s3"]


def test_hysteresis_preserves_active_entries_on_exit_threshold():
    policy = Policy(hysteresis=HysteresisRule(metric="score", enter=0.6, exit=0.4))
    metrics = {
        "s1": {"score": 0.45},
        "s2": {"score": 0.55},
    }

    assert evaluate_policy(metrics, policy, prev_active=["s1"]) == ["s1"]


def test_parse_policy_from_yaml_payload():
    raw = """
    thresholds:
      sharpe:
        metric: sharpe
        min: 0.7
    top_k:
      metric: sharpe
      k: 2
    hysteresis:
      metric: sharpe
      enter: 1.0
      exit: 0.8
    """

    parsed = parse_policy(raw)

    assert parsed.thresholds["sharpe"].min == 0.7
    assert parsed.top_k == TopKRule(metric="sharpe", k=2)
    assert parsed.hysteresis == HysteresisRule(metric="sharpe", enter=1.0, exit=0.8)
