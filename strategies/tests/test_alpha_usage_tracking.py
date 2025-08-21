"""Tests for alpha usage tracking functionality."""

import tempfile
from pathlib import Path
import yaml
import json

from scripts.track_alpha_usage import AlphaUsageTracker


def test_alpha_usage_tracker_basic():
    """Test basic functionality of alpha usage tracker."""
    tracker = AlphaUsageTracker()
    
    # Should start empty
    assert len(tracker.implemented_alphas) == 0
    assert len(tracker.used_alphas) == 0
    assert len(tracker.alpha_node_files) == 0
    
    # Test loading implemented alphas from actual registry
    tracker.load_implemented_alphas()
    assert len(tracker.implemented_alphas) > 0
    
    # Test scanning alpha node files
    tracker.scan_alpha_node_files()
    assert len(tracker.alpha_node_files) > 0
    
    # Test scanning strategy usage
    tracker.scan_strategy_usage()
    
    # Generate report
    report = tracker.generate_usage_report()
    assert "summary" in report
    assert "implemented_alphas" in report
    assert "usage" in report
    assert "files" in report
    
    # Check summary fields
    summary = report["summary"]
    assert "total_implemented" in summary
    assert "total_available_nodes" in summary
    assert "total_used" in summary
    assert "unused_count" in summary
    
    # Test table format
    table_output = tracker.format_table_report()
    assert "Alpha Usage Tracking Report" in table_output
    assert "USED ALPHAS" in table_output


def test_alpha_usage_tracker_detects_usage():
    """Test that tracker correctly detects alpha usage."""
    tracker = AlphaUsageTracker()
    tracker.load_implemented_alphas()
    tracker.scan_alpha_node_files()
    tracker.scan_strategy_usage()
    
    # Should detect composite_alpha usage in DAG
    assert "composite_alpha" in tracker.used_alphas
    
    # Should detect various alphas used by composite_alpha
    used_alpha_names = tracker.used_alphas.keys()
    expected_alphas = [
        "acceptable_price_band",
        "llrti",
        "latent_liquidity_alpha",
        "non_linear_alpha",
        "order_book_clustering_collapse",
        "quantum_liquidity_echo",
        "resiliency_alpha",
    ]
    
    for alpha in expected_alphas:
        assert alpha in used_alpha_names, f"Expected {alpha} to be detected as used"


def test_registry_update():
    """Test registry update functionality."""
    # Create temporary registry
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        test_registry = [
            {
                'doc': 'test/alpha1.md',
                'status': 'implemented',
                'modules': ['strategies/nodes/indicators/test_alpha.py'],
                'priority': 'normal',
                'tags': []
            }
        ]
        yaml.dump(test_registry, f)
        temp_registry_path = Path(f.name)
    
    try:
        tracker = AlphaUsageTracker()
        
        # Mock some usage data
        tracker.alpha_node_files = {'test_alpha': 'strategies/nodes/indicators/test_alpha.py'}
        tracker.used_alphas = {'test_alpha': ['test_strategy']}
        
        # Update registry
        tracker.update_registry_with_usage(temp_registry_path)
        
        # Verify update
        updated_data = yaml.safe_load(temp_registry_path.read_text())
        assert updated_data[0]['usage_status'] == 'used'
        assert 'test_strategy' in updated_data[0]['used_in_strategies']
        
    finally:
        temp_registry_path.unlink()


def test_json_output():
    """Test JSON output format."""
    tracker = AlphaUsageTracker()
    tracker.load_implemented_alphas()
    tracker.scan_alpha_node_files()
    tracker.scan_strategy_usage()
    
    report = tracker.generate_usage_report()
    
    # Should be valid JSON
    json_str = json.dumps(report, indent=2)
    parsed = json.loads(json_str)
    
    assert parsed == report


if __name__ == "__main__":
    test_alpha_usage_tracker_basic()
    test_alpha_usage_tracker_detects_usage()
    test_registry_update()
    test_json_output()
    print("All tests passed!")