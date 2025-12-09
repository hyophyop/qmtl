import yaml

from qmtl.services.worldservice.policy_engine import (
    CorrelationRule,
    HysteresisRule,
    Policy,
    PolicyEvaluationResult,
    ThresholdRule,
    TopKRule,
    evaluate_policy,
    parse_policy,
)


def test_threshold_filtering():
    policy = Policy(thresholds={"sharpe": ThresholdRule(metric="sharpe", min=0.5)})
    metrics = {"s1": {"sharpe": 0.6}, "s2": {"sharpe": 0.4}}
    result = evaluate_policy(metrics, policy)
    assert result.selected == ["s1"]
    perf = result.rule_results["s2"]["performance"]
    assert perf.status == "fail"
    assert perf.reason_code == "performance_thresholds_failed"


def test_topk_selection():
    policy = Policy(top_k=TopKRule(metric="sharpe", k=2))
    metrics = {
        "s1": {"sharpe": 1.0},
        "s2": {"sharpe": 0.8},
        "s3": {"sharpe": 1.5},
    }
    result = evaluate_policy(metrics, policy)
    assert result.selected == ["s3", "s1"]
    assert result.rule_results["s2"]["performance"].reason_code == "performance_rank_outside_top_k"


def test_topk_missing_metrics_sorted_last():
    policy = Policy(top_k=TopKRule(metric="sharpe", k=2))
    metrics = {
        "s1": {"sharpe": 1.0},
        "s2": {},
        "s3": {"sharpe": 0.4},
    }

    result = evaluate_policy(metrics, policy)
    assert result.selected == ["s1", "s3"]
    assert result.rule_results["s2"]["data_currency"].reason_code == "metrics_missing"


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

    result = evaluate_policy(metrics, policy)
    assert result.selected == ["s1"]
    assert result.rule_results["s2"]["performance"].status == "fail"


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

    result = evaluate_policy(metrics, policy, correlations=correlations)
    assert result.selected == ["s1", "s3"]
    assert result.rule_results["s2"]["risk_constraint"].reason_code == "correlation_constraint_failed"


def test_hysteresis_preserves_active_entries_on_exit_threshold():
    policy = Policy(hysteresis=HysteresisRule(metric="score", enter=0.6, exit=0.4))
    metrics = {
        "s1": {"score": 0.45},
        "s2": {"score": 0.55},
    }

    result = evaluate_policy(metrics, policy, prev_active=["s1"])
    assert result.selected == ["s1"]
    assert result.rule_results["s1"]["risk_constraint"].reason_code == "risk_constraints_ok"


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


def test_parse_policy_from_bytes_with_combined_rules():
    raw = yaml.safe_dump(
        {
            "thresholds": {"score": {"metric": "score", "min": 0.3}},
            "top_k": {"metric": "score", "k": 3},
            "correlation": {"max": 0.4},
            "hysteresis": {"metric": "score", "enter": 0.6, "exit": 0.4},
        }
    ).encode()

    policy = parse_policy(raw)
    metrics = {
        "s1": {"score": 0.9},
        "s2": {"score": 0.7},
        "s3": {"score": 0.45},
    }
    correlations = {("s1", "s2"): 0.1, ("s1", "s3"): 0.3, ("s2", "s3"): 0.2}

    selected = evaluate_policy(
        metrics,
        policy,
        prev_active=["s3"],
        correlations=correlations,
    )

    assert isinstance(selected, PolicyEvaluationResult)
    assert policy.thresholds["score"].min == 0.3
    assert set(selected.selected) == {"s1", "s2", "s3"}


def test_rule_results_include_expected_metadata():
    policy = Policy(
        thresholds={
            "sharpe": ThresholdRule(metric="sharpe", min=1.0),
            "max_drawdown": ThresholdRule(metric="max_drawdown", max=0.2),
        },
        correlation=CorrelationRule(max=0.5),
    )
    metrics = {
        "s1": {"sharpe": 1.2, "max_drawdown": 0.1, "num_trades": 25},
        "s2": {"sharpe": 1.1, "max_drawdown": 0.1},
    }
    correlations = {("s1", "s2"): 0.9}

    result = evaluate_policy(metrics, policy, correlations=correlations)

    assert result.rule_results["s1"]["data_currency"].status == "pass"
    assert result.rule_results["s1"]["sample"].severity == "soft"
    assert result.rule_results["s1"]["performance"].status == "pass"
    assert result.rule_results["s2"]["performance"].status == "pass"
    risk = result.rule_results["s2"]["risk_constraint"]
    assert risk.status == "fail"
    assert risk.reason_code == "correlation_constraint_failed"
    assert set(result.rule_results["s1"].keys()) >= {"data_currency", "sample", "performance", "risk_constraint"}


def test_validation_profiles_switch_by_stage():
    policy = parse_policy(
        {
            "validation_profiles": {
                "backtest": {
                    "sample": {"min_effective_years": 2.0, "min_trades_total": 100},
                    "performance": {"sharpe_min": 0.5, "max_dd_max": 0.3},
                },
                "paper": {
                    "sample": {"min_effective_years": 3.0},
                    "performance": {"sharpe_min": 0.8, "max_dd_max": 0.2, "gain_to_pain_min": 1.2},
                    "robustness": {"dsr_min": 0.25},
                    "risk": {"adv_utilization_p95_max": 0.3},
                },
            },
            "default_profile_by_stage": {"backtest_only": "backtest", "paper_only": "paper"},
            "selection": {"top_k": {"metric": "sharpe", "k": 1}},
        }
    )
    metrics = {
        "s1": {
            "effective_history_years": 2.5,
            "n_trades_total": 150,
            "sharpe": 0.65,
            "max_drawdown": 0.25,
            "gain_to_pain_ratio": 1.1,
            "deflated_sharpe_ratio": 0.3,
            "adv_utilization_p95": 0.25,
        }
    }

    backtest = evaluate_policy(metrics, policy, stage="backtest")
    paper = evaluate_policy(metrics, policy, stage="paper_only")

    assert backtest.profile == "backtest"
    assert backtest.selected == ["s1"]
    assert paper.profile == "paper"
    assert paper.selected == []
    assert paper.for_strategy("s1")["performance"].reason_code == "performance_thresholds_failed"


def test_selection_thresholds_alias_retained():
    policy = parse_policy({"selection": {"thresholds": {"sharpe": {"metric": "sharpe", "min": 0.6}}}})
    metrics = {"s1": {"sharpe": 0.7}, "s2": {"sharpe": 0.4}}

    result = evaluate_policy(metrics, policy)

    assert result.selected == ["s1"]
    assert policy.selection is not None
    assert "sharpe" in policy.selection.thresholds
