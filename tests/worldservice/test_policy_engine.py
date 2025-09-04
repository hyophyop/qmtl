from qmtl.worldservice.policy_engine import (
    Policy,
    ThresholdRule,
    TopKRule,
    evaluate_policy,
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
