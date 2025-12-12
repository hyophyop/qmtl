from __future__ import annotations

import sys
from pathlib import Path

import yaml

from scripts.generate_validation_report import generate_markdown_report, main


def _sample_evaluation_run() -> dict:
    return {
        "world_id": "world-demo",
        "strategy_id": "strat-a",
        "run_id": "eval-123",
        "stage": "backtest",
        "risk_tier": "medium",
        "summary": {"status": "warn", "recommended_stage": "paper_only"},
        "validation": {
            "policy_version": "v1",
            "ruleset_hash": "abc123",
            "extended_revision": 2,
            "extended_evaluated_at": "2025-12-10T00:00:00Z",
            "profile": "backtest",
            "results": {
                "performance.sharpe_min": {
                    "status": "pass",
                    "severity": "blocking",
                    "owner": "quant",
                    "reason_code": "performance_ok",
                    "reason": "Sharpe above target",
                },
                "robustness.dsr_min": {
                "status": "fail",
                "severity": "soft",
                "owner": "risk",
                "reason_code": "dsr_low",
                "reason": "DSR below target",
                "tags": ["robustness"],
            },
            "cohort": {
                "status": "warn",
                "severity": "soft",
                "owner": "risk",
                "reason_code": "cohort_median_sharpe_below_min",
                "reason": "Median Sharpe below cohort min",
                "tags": ["cohort"],
            },
        },
    },
    "metrics": {
        "returns": {"sharpe": 1.2, "max_drawdown": 0.1},
        "sample": {"n_trades_total": 120},
        },
    }


def _sample_model_card() -> dict:
    return {
        "strategy_id": "strat-a",
        "model_card_version": "v1.0",
        "objective": "Capture medium-term momentum",
        "universe": "US equities",
        "data_sources": ["ohlcv"],
        "features": ["ma_crossover"],
        "assumptions": ["trend persists"],
        "limitations": ["drawdown sensitivity"],
    }


def test_generate_markdown_report_includes_core_fields() -> None:
    report = generate_markdown_report(_sample_evaluation_run(), _sample_model_card())

    assert "Validation Report — strat-a @ world-demo" in report
    assert "- Run ID: eval-123" in report
    assert "- Stage: backtest" in report
    assert "- Recommended stage: paper_only" in report
    assert "- Extended revision: 2" in report
    assert "- Extended evaluated_at: 2025-12-10T00:00:00Z" in report
    assert "| robustness.dsr_min | FAIL" in report
    assert "| performance.sharpe_min | PASS" in report
    assert "returns.sharpe" in report
    assert report.index("robustness.dsr_min") < report.index("performance.sharpe_min")
    assert "Extended validation" in report


def test_cli_writes_report_file(tmp_path: Path, monkeypatch, capsys) -> None:
    eval_path = tmp_path / "run.yaml"
    card_path = tmp_path / "card.yaml"
    out_path = tmp_path / "report.md"

    eval_path.write_text(yaml.safe_dump(_sample_evaluation_run()), encoding="utf-8")
    card_path.write_text(yaml.safe_dump(_sample_model_card()), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_validation_report",
            "--evaluation-run",
            str(eval_path),
            "--model-card",
            str(card_path),
            "--output",
            str(out_path),
        ],
    )

    main()

    report = out_path.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert "Validation Report — strat-a @ world-demo" in report
    assert "written to" in captured.out
    assert "Extended validation" in report
