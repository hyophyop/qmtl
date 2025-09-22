"""Tests for risk management controls."""

import pytest
import math
from qmtl.sdk.risk_management import (
    RiskManager, PositionInfo, RiskViolation, RiskViolationType
)


class TestPositionInfo:
    """Test PositionInfo functionality."""
    
    def test_position_info_properties(self):
        """Test PositionInfo calculated properties."""
        position = PositionInfo(
            symbol="AAPL",
            quantity=100,
            market_value=10000,
            unrealized_pnl=500,
            entry_price=95.0,
            current_price=100.0
        )
        
        assert position.exposure == 10000  # abs(market_value)
        
        # Test negative market value
        position_short = PositionInfo(
            symbol="TSLA",
            quantity=-50,
            market_value=-5000,
            unrealized_pnl=-200,
            entry_price=110.0,
            current_price=100.0
        )
        
        assert position_short.exposure == 5000  # abs(-5000)


class TestRiskViolation:
    """Test RiskViolation functionality."""
    
    def test_violation_severity_calculation(self):
        """Test severity calculation based on limit exceedance."""
        # Low severity (< 1.2x limit)
        violation_low = RiskViolation(
            violation_type=RiskViolationType.POSITION_SIZE_LIMIT,
            current_value=110,
            limit_value=100,
            description="Test",
            timestamp=1000
        )
        assert violation_low.severity == "low"
        
        # Medium severity (1.2x - 1.5x limit)
        violation_medium = RiskViolation(
            violation_type=RiskViolationType.LEVERAGE_LIMIT,
            current_value=130,
            limit_value=100,
            description="Test",
            timestamp=1000
        )
        assert violation_medium.severity == "medium"
        
        # High severity (1.5x - 2.0x limit)
        violation_high = RiskViolation(
            violation_type=RiskViolationType.DRAWDOWN_LIMIT,
            current_value=180,
            limit_value=100,
            description="Test",
            timestamp=1000
        )
        assert violation_high.severity == "high"
        
        # Critical severity (>= 2.0x limit)
        violation_critical = RiskViolation(
            violation_type=RiskViolationType.CONCENTRATION_LIMIT,
            current_value=250,
            limit_value=100,
            description="Test",
            timestamp=1000
        )
        assert violation_critical.severity == "critical"


class TestRiskManager:
    """Test RiskManager functionality."""
    
    def test_default_initialization(self):
        """Test default risk manager initialization."""
        risk_manager = RiskManager()
        
        assert risk_manager.max_leverage == 3.0
        assert risk_manager.max_drawdown_pct == 0.15
        assert risk_manager.max_concentration_pct == 0.20
        assert risk_manager.position_size_limit_pct == 0.10
        assert risk_manager.enable_dynamic_sizing is True
        assert risk_manager.max_position_size is None
    
    def test_custom_initialization(self):
        """Test custom risk manager initialization."""
        risk_manager = RiskManager(
            max_position_size=50000,
            max_leverage=2.0,
            max_drawdown_pct=0.10,
            max_concentration_pct=0.15,
            position_size_limit_pct=0.05,
            enable_dynamic_sizing=False
        )
        
        assert risk_manager.max_position_size == 50000
        assert risk_manager.max_leverage == 2.0
        assert risk_manager.max_drawdown_pct == 0.10
        assert risk_manager.max_concentration_pct == 0.15
        assert risk_manager.position_size_limit_pct == 0.05
        assert risk_manager.enable_dynamic_sizing is False
    
    def test_validate_position_size_within_limits(self):
        """Test position size validation when within limits."""
        risk_manager = RiskManager(
            max_position_size=10000,
            position_size_limit_pct=0.10
        )
        
        is_valid, violation, adjusted_quantity = risk_manager.validate_position_size(
            symbol="AAPL",
            proposed_quantity=50,  # $5000 value
            current_price=100.0,
            portfolio_value=100000,
            current_positions={}
        )
        
        assert is_valid
        assert violation is None
        assert adjusted_quantity == 50
    
    def test_validate_position_size_absolute_limit_exceeded(self):
        """Test position size validation when absolute limit exceeded."""
        risk_manager = RiskManager(
            max_position_size=5000,
            enable_dynamic_sizing=True
        )
        
        is_valid, violation, adjusted_quantity = risk_manager.validate_position_size(
            symbol="AAPL",
            proposed_quantity=100,  # $10000 value > $5000 limit
            current_price=100.0,
            portfolio_value=100000,
            current_positions={}
        )
        
        assert not is_valid
        assert violation is not None
        assert violation.violation_type == RiskViolationType.POSITION_SIZE_LIMIT
        assert adjusted_quantity == 50  # Adjusted to $5000 / $100 = 50 shares
    
    def test_validate_position_size_percentage_limit_exceeded(self):
        """Test position size validation when percentage limit exceeded."""
        risk_manager = RiskManager(
            position_size_limit_pct=0.05,  # 5% limit
            enable_dynamic_sizing=True
        )
        
        is_valid, violation, adjusted_quantity = risk_manager.validate_position_size(
            symbol="AAPL",
            proposed_quantity=80,  # $8000 value = 8% of $100k portfolio
            current_price=100.0,
            portfolio_value=100000,
            current_positions={}
        )
        
        assert not is_valid
        assert violation is not None
        assert violation.violation_type == RiskViolationType.POSITION_SIZE_LIMIT
        assert adjusted_quantity == 50  # Adjusted to 5% of $100k = $5000 / $100 = 50 shares
    
    def test_validate_position_size_no_dynamic_sizing(self):
        """Test position size validation without dynamic sizing."""
        risk_manager = RiskManager(
            max_position_size=5000,
            enable_dynamic_sizing=False
        )
        
        is_valid, violation, adjusted_quantity = risk_manager.validate_position_size(
            symbol="AAPL",
            proposed_quantity=100,  # $10000 value > $5000 limit
            current_price=100.0,
            portfolio_value=100000,
            current_positions={}
        )
        
        assert not is_valid
        assert violation is not None
        assert adjusted_quantity == 0.0  # No dynamic sizing, so zero quantity
    
    def test_validate_portfolio_risk_leverage_violation(self):
        """Test portfolio risk validation with leverage violation."""
        risk_manager = RiskManager(max_leverage=2.0)
        
        positions = {
            "AAPL": PositionInfo("AAPL", 100, 10000, 0, 100, 100),
            "TSLA": PositionInfo("TSLA", 200, 20000, 0, 100, 100),
            "MSFT": PositionInfo("MSFT", 300, 30000, 0, 100, 100),
        }
        
        violations = risk_manager.validate_portfolio_risk(
            positions=positions,
            portfolio_value=20000,  # Total exposure $60k, portfolio $20k = 3x leverage > 2x limit
            timestamp=1000
        )
        
        leverage_violations = [v for v in violations if v.violation_type == RiskViolationType.LEVERAGE_LIMIT]
        assert len(leverage_violations) >= 1
        assert leverage_violations[0].current_value == 3.0  # 60k / 20k
        assert leverage_violations[0].limit_value == 2.0
    
    def test_validate_portfolio_risk_concentration_violation(self):
        """Test portfolio risk validation with concentration violation."""
        risk_manager = RiskManager(max_concentration_pct=0.20)  # 20% limit
        
        positions = {
            "AAPL": PositionInfo("AAPL", 300, 30000, 0, 100, 100),  # 30% of portfolio
            "TSLA": PositionInfo("TSLA", 100, 10000, 0, 100, 100),  # 10% of portfolio
        }
        
        violations = risk_manager.validate_portfolio_risk(
            positions=positions,
            portfolio_value=100000,
            timestamp=1000
        )
        
        concentration_violations = [v for v in violations if v.violation_type == RiskViolationType.CONCENTRATION_LIMIT]
        assert len(concentration_violations) >= 1
        assert concentration_violations[0].symbol == "AAPL"
        assert concentration_violations[0].current_value == 0.30  # 30%
        assert concentration_violations[0].limit_value == 0.20   # 20%

    def test_validate_world_risk_concentration_violation(self):
        """Test world-scoped risk evaluation across strategies."""
        risk_manager = RiskManager(max_concentration_pct=0.40)

        strat_a_positions = {
            "AAPL": PositionInfo("AAPL", 100, 10000, 0, 100, 100),
        }
        strat_b_positions = {
            "AAPL": PositionInfo("AAPL", 100, 10000, 0, 100, 100),
        }

        # Each strategy individually holds 100% AAPL exposure on a $10k portfolio.
        # Combined world exposure remains 100% of the $20k aggregate, breaching the 40% limit.
        violations = risk_manager.validate_world_risk(
            strategies=[
                (10000, strat_a_positions),
                (10000, strat_b_positions),
            ],
            timestamp=0,
        )

        concentration_violations = [
            v for v in violations if v.violation_type == RiskViolationType.CONCENTRATION_LIMIT
        ]
        assert concentration_violations
        assert concentration_violations[0].current_value == 1.0
        assert concentration_violations[0].limit_value == 0.40
    
    def test_validate_portfolio_risk_drawdown_violation(self):
        """Test portfolio risk validation with drawdown violation."""
        risk_manager = RiskManager(max_drawdown_pct=0.10)  # 10% limit

        positions = {
            "AAPL": PositionInfo("AAPL", 100, 10000, -5000, 100, 100),
        }

        # Establish peak portfolio value
        risk_manager.validate_portfolio_risk(
            positions=positions,
            portfolio_value=100000,
            timestamp=0,
        )

        violations = risk_manager.validate_portfolio_risk(
            positions=positions,
            portfolio_value=80000,  # 20% drawdown from peak of 100k
            timestamp=1000
        )
        
        drawdown_violations = [v for v in violations if v.violation_type == RiskViolationType.DRAWDOWN_LIMIT]
        assert len(drawdown_violations) >= 1
        assert drawdown_violations[0].current_value == 0.20  # 20% drawdown
        assert drawdown_violations[0].limit_value == 0.10   # 10% limit
    
    def test_calculate_position_size_basic(self):
        """Test basic position size calculation."""
        risk_manager = RiskManager(position_size_limit_pct=0.10)
        
        position_size = risk_manager.calculate_position_size(
            symbol="AAPL",
            target_allocation_pct=0.05,  # 5% target
            current_price=100.0,
            portfolio_value=100000
        )
        
        # Should be 5% of $100k = $5k / $100 = 50 shares
        assert position_size == 50.0
    
    def test_calculate_position_size_with_volatility_adjustment(self):
        """Test position size calculation with volatility adjustment."""
        risk_manager = RiskManager(position_size_limit_pct=0.10)
        
        # High volatility should reduce position size
        position_size_high_vol = risk_manager.calculate_position_size(
            symbol="CRYPTO",
            target_allocation_pct=0.05,
            current_price=100.0,
            portfolio_value=100000,
            current_volatility=0.80  # 80% volatility
        )
        
        # Low volatility should maintain position size
        position_size_low_vol = risk_manager.calculate_position_size(
            symbol="BOND",
            target_allocation_pct=0.05,
            current_price=100.0,
            portfolio_value=100000,
            current_volatility=0.05  # 5% volatility
        )
        
        assert position_size_high_vol < position_size_low_vol
        assert position_size_high_vol > 0  # Should still be positive
    
    def test_calculate_position_size_edge_cases(self):
        """Test position size calculation edge cases."""
        risk_manager = RiskManager()
        
        # Zero portfolio value
        position_size = risk_manager.calculate_position_size(
            symbol="AAPL",
            target_allocation_pct=0.05,
            current_price=100.0,
            portfolio_value=0.0
        )
        assert position_size == 0.0
        
        # Zero price
        position_size = risk_manager.calculate_position_size(
            symbol="AAPL",
            target_allocation_pct=0.05,
            current_price=0.0,
            portfolio_value=100000
        )
        assert position_size == 0.0
    
    def test_get_risk_summary(self):
        """Test risk summary generation."""
        risk_manager = RiskManager()

        # Add some test violations
        risk_manager.violations = [
            RiskViolation(RiskViolationType.LEVERAGE_LIMIT, 3.0, 2.0, "Test", 1000),
            RiskViolation(RiskViolationType.POSITION_SIZE_LIMIT, 150, 100, "Test", 1000),
        ]

        risk_manager.validate_portfolio_risk({}, 100000, timestamp=0)
        risk_manager.validate_portfolio_risk({}, 90000, timestamp=1000)

        summary = risk_manager.get_risk_summary()

        assert summary["total_violations"] == 2
        assert summary["violation_types"][RiskViolationType.LEVERAGE_LIMIT.value] == 1
        assert summary["violation_types"][RiskViolationType.POSITION_SIZE_LIMIT.value] == 1
        assert summary["peak_portfolio_value"] == 100000
        assert summary["current_drawdown"] == pytest.approx(0.1)
        assert "risk_config" in summary


def test_integration_risk_workflow():
    """Test integrated risk management workflow."""
    risk_manager = RiskManager(
        max_leverage=2.0,
        max_concentration_pct=0.25,
        position_size_limit_pct=0.10,
        max_drawdown_pct=0.15
    )
    
    # Test position sizing
    position_size = risk_manager.calculate_position_size(
        symbol="AAPL",
        target_allocation_pct=0.08,
        current_price=150.0,
        portfolio_value=100000
    )
    
    # Should be 8% of portfolio = $8000 / $150 = 53.33 shares
    assert abs(position_size - 53.33) < 0.1
    
    # Test position validation
    is_valid, violation, adjusted = risk_manager.validate_position_size(
        symbol="AAPL",
        proposed_quantity=position_size,
        current_price=150.0,
        portfolio_value=100000,
        current_positions={}
    )
    
    assert is_valid  # Should be within limits
    assert violation is None
    
    # Test portfolio risk validation
    positions = {
        "AAPL": PositionInfo("AAPL", position_size, position_size * 150, 0, 150, 150),
        "TSLA": PositionInfo("TSLA", 20, 20 * 200, 0, 200, 200),  # $4000 position
    }
    
    violations = risk_manager.validate_portfolio_risk(
        positions=positions,
        portfolio_value=100000,
        timestamp=1000
    )
    
    # Should have no violations as positions are within limits
    assert len(violations) == 0
    
    # Get risk summary
    summary = risk_manager.get_risk_summary()
    assert summary["total_violations"] == 0
    assert summary["peak_portfolio_value"] == 100000
