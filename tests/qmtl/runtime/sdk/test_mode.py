"""Tests for QMTL v2.0 Mode utilities (Phase 3)."""

from __future__ import annotations

import pytest

from qmtl.runtime.sdk.mode import (
    Mode,
    mode_to_execution_domain,
    execution_domain_to_mode,
    effective_mode_to_mode,
    is_orders_enabled,
    is_real_time_data,
    normalize_mode,
)


class TestMode:
    """Tests for Mode enum."""

    def test_mode_values(self):
        """Test Mode enum values."""
        assert Mode.BACKTEST == "backtest"
        assert Mode.PAPER == "paper"
        assert Mode.LIVE == "live"

    def test_mode_from_string(self):
        """Test Mode creation from string."""
        assert Mode("backtest") == Mode.BACKTEST
        assert Mode("paper") == Mode.PAPER
        assert Mode("live") == Mode.LIVE

    def test_mode_invalid(self):
        """Test Mode with invalid value raises error."""
        with pytest.raises(ValueError):
            Mode("invalid")


class TestModeToExecutionDomain:
    """Tests for mode_to_execution_domain."""

    def test_backtest_to_backtest(self):
        """Backtest mode maps to backtest domain."""
        assert mode_to_execution_domain(Mode.BACKTEST) == "backtest"

    def test_paper_to_dryrun(self):
        """Paper mode maps to dryrun domain."""
        assert mode_to_execution_domain(Mode.PAPER) == "dryrun"

    def test_live_to_live(self):
        """Live mode maps to live domain."""
        assert mode_to_execution_domain(Mode.LIVE) == "live"

    def test_string_input(self):
        """String mode input is handled."""
        assert mode_to_execution_domain("backtest") == "backtest"
        assert mode_to_execution_domain("paper") == "dryrun"
        assert mode_to_execution_domain("live") == "live"


class TestExecutionDomainToMode:
    """Tests for execution_domain_to_mode."""

    def test_backtest_domain(self):
        """Backtest domain maps to BACKTEST mode."""
        assert execution_domain_to_mode("backtest") == Mode.BACKTEST

    def test_dryrun_domain(self):
        """Dryrun domain maps to PAPER mode."""
        assert execution_domain_to_mode("dryrun") == Mode.PAPER

    def test_live_domain(self):
        """Live domain maps to LIVE mode."""
        assert execution_domain_to_mode("live") == Mode.LIVE

    def test_shadow_domain(self):
        """Shadow domain maps to BACKTEST mode for safety."""
        assert execution_domain_to_mode("shadow") == Mode.BACKTEST

    def test_none_domain(self):
        """None domain defaults to BACKTEST."""
        assert execution_domain_to_mode(None) == Mode.BACKTEST

    def test_default_domain(self):
        """Default domain maps to BACKTEST."""
        assert execution_domain_to_mode("default") == Mode.BACKTEST


class TestEffectiveModeToMode:
    """Tests for effective_mode_to_mode."""

    def test_validate_mode(self):
        """WS validate maps to BACKTEST."""
        assert effective_mode_to_mode("validate") == Mode.BACKTEST

    def test_compute_only_mode(self):
        """WS compute-only maps to BACKTEST."""
        assert effective_mode_to_mode("compute-only") == Mode.BACKTEST

    def test_paper_mode(self):
        """WS paper maps to PAPER."""
        assert effective_mode_to_mode("paper") == Mode.PAPER

    def test_live_mode(self):
        """WS live maps to LIVE."""
        assert effective_mode_to_mode("live") == Mode.LIVE

    def test_shadow_mode(self):
        """WS shadow maps to BACKTEST for safety."""
        assert effective_mode_to_mode("shadow") == Mode.BACKTEST

    def test_none_mode(self):
        """None effective_mode defaults to BACKTEST."""
        assert effective_mode_to_mode(None) == Mode.BACKTEST


class TestIsOrdersEnabled:
    """Tests for is_orders_enabled."""

    def test_backtest_no_orders(self):
        """Backtest mode has orders disabled."""
        assert is_orders_enabled(Mode.BACKTEST) is False

    def test_paper_no_real_orders(self):
        """Paper mode has real orders disabled."""
        assert is_orders_enabled(Mode.PAPER) is False

    def test_live_orders_enabled(self):
        """Live mode has orders enabled."""
        assert is_orders_enabled(Mode.LIVE) is True

    def test_string_input(self):
        """String mode input is handled."""
        assert is_orders_enabled("backtest") is False
        assert is_orders_enabled("paper") is False
        assert is_orders_enabled("live") is True


class TestIsRealTimeData:
    """Tests for is_real_time_data."""

    def test_backtest_not_realtime(self):
        """Backtest does not use real-time data."""
        assert is_real_time_data(Mode.BACKTEST) is False

    def test_paper_is_realtime(self):
        """Paper mode uses real-time data."""
        assert is_real_time_data(Mode.PAPER) is True

    def test_live_is_realtime(self):
        """Live mode uses real-time data."""
        assert is_real_time_data(Mode.LIVE) is True

    def test_string_input(self):
        """String mode input is handled."""
        assert is_real_time_data("backtest") is False
        assert is_real_time_data("paper") is True
        assert is_real_time_data("live") is True


class TestNormalizeMode:
    """Tests for normalize_mode."""

    def test_mode_enum_passthrough(self):
        """Mode enum is returned as-is."""
        assert normalize_mode(Mode.BACKTEST) == Mode.BACKTEST
        assert normalize_mode(Mode.PAPER) == Mode.PAPER
        assert normalize_mode(Mode.LIVE) == Mode.LIVE

    def test_backtest_aliases(self):
        """Backtest aliases normalize correctly."""
        assert normalize_mode("backtest") == Mode.BACKTEST
        assert normalize_mode("BACKTEST") == Mode.BACKTEST
        assert normalize_mode("backtesting") == Mode.BACKTEST
        assert normalize_mode("offline") == Mode.BACKTEST
        assert normalize_mode("sandbox") == Mode.BACKTEST
        assert normalize_mode("validate") == Mode.BACKTEST

    def test_paper_aliases(self):
        """Paper aliases normalize correctly."""
        assert normalize_mode("paper") == Mode.PAPER
        assert normalize_mode("PAPER") == Mode.PAPER
        assert normalize_mode("dryrun") == Mode.PAPER
        assert normalize_mode("dry_run") == Mode.PAPER
        assert normalize_mode("sim") == Mode.PAPER
        assert normalize_mode("simulation") == Mode.PAPER

    def test_live_aliases(self):
        """Live aliases normalize correctly."""
        assert normalize_mode("live") == Mode.LIVE
        assert normalize_mode("LIVE") == Mode.LIVE
        assert normalize_mode("prod") == Mode.LIVE
        assert normalize_mode("production") == Mode.LIVE

    def test_unknown_defaults_to_backtest(self):
        """Unknown values default to BACKTEST."""
        assert normalize_mode("unknown") == Mode.BACKTEST
        assert normalize_mode("") == Mode.BACKTEST
        assert normalize_mode(None) == Mode.BACKTEST
        assert normalize_mode(123) == Mode.BACKTEST


class TestModeRoundTrip:
    """Tests for mode conversion round-trips."""

    def test_mode_to_domain_to_mode(self):
        """Mode → domain → mode round-trip preserves value."""
        for mode in Mode:
            domain = mode_to_execution_domain(mode)
            result = execution_domain_to_mode(domain)
            assert result == mode, f"Round-trip failed for {mode}"

    def test_ws_mode_to_user_mode(self):
        """WorldService modes map correctly to user modes."""
        ws_to_user = [
            ("validate", Mode.BACKTEST),
            ("compute-only", Mode.BACKTEST),
            ("paper", Mode.PAPER),
            ("live", Mode.LIVE),
        ]
        for ws_mode, expected in ws_to_user:
            assert effective_mode_to_mode(ws_mode) == expected
