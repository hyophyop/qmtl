import yaml

import qmtl.services.worldservice.policy_engine as pe

from qmtl.services.worldservice.policy_engine import (
    CorrelationRule,
    HysteresisRule,
    Policy,
    PolicyEvaluationResult,
    RobustnessRule,
    RuleContext,
    ValidationConfig,
    evaluate_extended_layers,
    evaluate_cohort_rules,
    evaluate_live_monitoring,
    evaluate_portfolio_rules,
    evaluate_stress_rules,
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


def test_validation_missing_metric_warn_allows_selection_and_warns():
    policy = Policy(
        thresholds={"sharpe": ThresholdRule(metric="sharpe", min=0.5)},
        validation=ValidationConfig(on_missing_metric="warn"),
    )
    metrics = {"s1": {}}

    result = evaluate_policy(metrics, policy)

    assert result.selected == ["s1"]
    data_currency = result.rule_results["s1"]["data_currency"]
    assert data_currency.status == "warn"
    perf = result.rule_results["s1"]["performance"]
    assert perf.status == "warn"
    assert perf.reason_code == "performance_metrics_missing"


def test_validation_missing_metric_ignore_sets_info_severity():
    policy = Policy(
        thresholds={"sharpe": ThresholdRule(metric="sharpe", min=0.5)},
        validation=ValidationConfig(on_missing_metric="ignore"),
    )
    metrics = {"s1": {}}

    result = evaluate_policy(metrics, policy)

    assert result.selected == ["s1"]
    data_currency = result.rule_results["s1"]["data_currency"]
    assert data_currency.status == "warn"
    assert data_currency.severity == "info"
    assert result.rule_results["s1"]["performance"].status == "pass"


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


def test_on_error_warn_converts_rule_exception(monkeypatch):
    policy = Policy(validation=ValidationConfig(on_error="warn"))
    metrics = {"s1": {"sharpe": 1.0}}

    def _boom(self, metrics, context):
        raise RuntimeError("explode")

    monkeypatch.setattr(pe.DataCurrencyRule, "evaluate", _boom, raising=True)

    result = evaluate_policy(metrics, policy)

    rule = result.rule_results["s1"]["data_currency"]
    assert rule.status == "warn"
    assert rule.reason_code == "rule_error"
    assert "explode" in rule.reason


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


def test_evaluate_policy_exposes_metadata():
    policy = parse_policy({"thresholds": {"sharpe": {"metric": "sharpe", "min": 0.5}}})
    metrics = {"s1": {"sharpe": 0.8}}

    result = evaluate_policy(metrics, policy, stage="backtest", policy_version="3")
    repeat = evaluate_policy(metrics, policy, stage="backtest", policy_version="3")

    assert result.policy_version == "3"
    assert result.ruleset_hash is not None and result.ruleset_hash.startswith("blake3:")
    assert result.ruleset_hash == repeat.ruleset_hash
    assert result.recommended_stage == "backtest_only"


def test_selection_thresholds_alias_retained():
    policy = parse_policy({"selection": {"thresholds": {"sharpe": {"metric": "sharpe", "min": 0.6}}}})
    metrics = {"s1": {"sharpe": 0.7}, "s2": {"sharpe": 0.4}}

    result = evaluate_policy(metrics, policy)

    assert result.selected == ["s1"]
    assert policy.selection is not None
    assert "sharpe" in policy.selection.thresholds


def test_validation_profile_overrides_severity_and_owner():
    policy = parse_policy(
        {
            "validation_profiles": {
                "backtest": {
                    "sample": {
                        "min_effective_years": 3.0,
                        "severity": "blocking",
                        "owner": "risk",
                    },
                    "performance": {
                        "sharpe_min": 1.0,
                        "severity": "soft",
                        "owner": "quant",
                    },
                    "risk": {
                        "adv_utilization_p95_max": 0.5,
                        "severity": "soft",
                        "owner": "ops",
                    },
                }
            },
            "default_profile_by_stage": {"backtest_only": "backtest"},
            "correlation": {"max": 0.9},
        }
    )
    metrics = {"s1": {"effective_history_years": 2.0, "sharpe": 0.8, "adv_utilization_p95": 0.2}}

    result = evaluate_policy(metrics, policy, stage="backtest")
    sample = result.for_strategy("s1")["sample"]
    perf = result.for_strategy("s1")["performance"]
    risk = result.for_strategy("s1")["risk_constraint"]

    assert sample.severity == "blocking"
    assert sample.owner == "risk"
    assert perf.severity == "soft"
    assert perf.owner == "quant"
    assert risk.severity == "soft"
    assert risk.owner == "ops"


def test_parse_policy_with_p5_sections():
    payload = {
        "cohort": {"top_k": 3, "severity": "soft", "owner": "risk"},
        "portfolio": {"max_incremental_var_99": 0.4},
        "stress": {"severity": "info", "owner": "ops", "scenarios": {"crash": {"dd_max": 0.3}}},
        "live_monitoring": {"lookback_days": 30, "decay_threshold": 0.8},
    }
    policy = parse_policy(payload)
    assert policy.cohort is not None
    assert policy.portfolio is not None
    assert policy.stress is not None
    assert policy.live_monitoring is not None


def test_stub_cohort_portfolio_stress_and_live_monitoring():
    policy = parse_policy(
        {
            "cohort": {"severity": "soft", "owner": "risk"},
            "portfolio": {"severity": "soft", "owner": "ops"},
            "stress": {"severity": "info", "owner": "ops"},
            "live_monitoring": {"severity": "soft", "owner": "risk"},
        }
    )
    metrics = {"s1": {"sharpe": 1.0}, "s2": {"sharpe": 0.5}}

    cohort_results = evaluate_cohort_rules(metrics, policy)
    portfolio_results = evaluate_portfolio_rules(metrics, policy)
    stress_results = evaluate_stress_rules(metrics, policy)
    live_monitoring_result = evaluate_live_monitoring(metrics, policy)

    assert set(cohort_results.keys()) == {"s1", "s2"}
    assert all(result.reason_code.startswith("cohort_") or result.reason_code == "cohort_ok" for result in cohort_results.values())
    assert all(result.reason_code.startswith("portfolio_") or result.reason_code == "portfolio_ok" for result in portfolio_results.values())
    assert all(result.reason_code.startswith("stress_") or result.reason_code == "stress_ok" for result in stress_results.values())
    assert live_monitoring_result is not None
    assert live_monitoring_result.reason_code in {"live_monitoring_ok", "live_sharpe_missing"}


def test_evaluate_extended_layers_over_runs():
    runs = [
        {
            "strategy_id": "s1",
            "metrics": {
                "returns": {"sharpe": 1.1},
                "risk": {"incremental_var_99": 0.4, "incremental_es_99": 0.3},
                "stress": {"crash": {"max_drawdown": 0.25}},
                "diagnostics": {"live_sharpe": 0.9, "live_max_drawdown": 0.2},
            },
        },
        {
            "strategy_id": "s2",
            "metrics": {
                "returns": {"sharpe": 0.6},
                "risk": {"incremental_var_99": 0.6},
                "diagnostics": {"live_sharpe": 0.5, "live_max_drawdown": 0.35},
            },
        },
    ]
    policy = parse_policy(
        {
            "cohort": {"top_k": 1, "sharpe_median_min": 0.8},
            "portfolio": {"max_incremental_var_99": 0.5, "min_portfolio_sharpe_uplift": 0.1},
            "stress": {"scenarios": {"crash": {"dd_max": 0.3}}},
            "live_monitoring": {"sharpe_min": 0.7, "dd_max": 0.3},
        }
    )

    results = evaluate_extended_layers(runs, policy, stage="paper")

    assert set(results.keys()) == {"s1", "s2"}
    assert "cohort" in results["s2"]
    assert "portfolio" in results["s2"]
    assert "stress" in results["s1"]
    assert "live_monitoring" in results["s1"]
    assert results["s2"]["portfolio"].status in {"fail", "warn"}


def test_validation_config_default_values():
    """§7.4 of validation architecture: on_error and on_missing_metric defaults."""
    policy = Policy()
    assert policy.validation.on_error == "fail"
    assert policy.validation.on_missing_metric == "fail"


def test_validation_config_custom_values():
    """§7.4 of validation architecture: custom on_error/on_missing_metric."""
    policy = parse_policy(
        {
            "validation": {
                "on_error": "warn",
                "on_missing_metric": "ignore",
            }
        }
    )
    assert policy.validation.on_error == "warn"
    assert policy.validation.on_missing_metric == "ignore"


def test_robustness_rule_passes_when_dsr_above_min():
    """§3.1 RobustnessRule: passes when DSR is above threshold."""
    rule = RobustnessRule(dsr_min=0.3)
    ctx = RuleContext(strategy_id="s1")
    metrics = {"deflated_sharpe_ratio": 0.5}
    result = rule.evaluate(metrics, ctx)
    assert result.status == "pass"
    assert result.reason_code == "robustness_ok"


def test_robustness_rule_fails_when_dsr_below_min():
    """§3.1 RobustnessRule: fails when DSR is below threshold."""
    rule = RobustnessRule(dsr_min=0.5, severity="blocking", owner="risk")
    ctx = RuleContext(strategy_id="s1")
    metrics = {"deflated_sharpe_ratio": 0.3}
    result = rule.evaluate(metrics, ctx)
    assert result.status == "fail"
    assert result.reason_code == "dsr_below_min"
    assert result.severity == "blocking"
    assert result.owner == "risk"


def test_robustness_rule_warns_when_dsr_missing():
    """§3.1 RobustnessRule: warns when DSR metric is missing."""
    rule = RobustnessRule(dsr_min=0.3)
    ctx = RuleContext(strategy_id="s1")
    metrics = {"sharpe": 1.0}
    result = rule.evaluate(metrics, ctx)
    assert result.status == "warn"
    assert result.reason_code == "dsr_missing"


def test_robustness_rule_cv_sharpe_gap_exceeds_max():
    """§3.1 RobustnessRule: fails when train/test sharpe gap exceeds max."""
    rule = RobustnessRule(cv_sharpe_gap_max=0.3)
    ctx = RuleContext(strategy_id="s1")
    metrics = {"sharpe_first_half": 1.0, "sharpe_second_half": 1.5}  # gap = 0.5
    result = rule.evaluate(metrics, ctx)
    assert result.status == "fail"
    assert result.reason_code == "cv_sharpe_gap_exceeds_max"
    assert result.details.get("sharpe_gap") == 0.5


def test_robustness_rule_included_in_evaluate_policy():
    """§9.4 RobustnessRule is part of the v1 core rule set."""
    policy = parse_policy(
        {
            "validation_profiles": {
                "backtest": {
                    "robustness": {"dsr_min": 0.4, "cv_sharpe_gap_max": 0.3},
                }
            },
            "default_profile_by_stage": {"backtest_only": "backtest"},
        }
    )
    metrics = {
        "s1": {
            "sharpe": 1.0,
            "deflated_sharpe_ratio": 0.5,
            "sharpe_first_half": 1.0,
            "sharpe_second_half": 1.2,
        }
    }
    result = evaluate_policy(metrics, policy, stage="backtest")
    assert "robustness" in result.for_strategy("s1")
    robustness = result.for_strategy("s1")["robustness"]
    assert robustness.status == "pass"
