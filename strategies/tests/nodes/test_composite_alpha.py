from strategies.nodes.indicators.composite_alpha import composite_alpha_node


def test_composite_alpha_returns_mean_alpha():
    """Test that composite alpha correctly computes mean of all components."""
    # Test with default empty data
    data = {}
    result = composite_alpha_node(data)
    components = result["components"]
    expected = sum(components.values()) / len(components)
    assert result["alpha"] == expected

    # Verify we now have 9 components (including the previously unused alphas)
    assert len(components) == 9
    assert "acceptable_price_band" in components
    assert "gap_amplification" in components
    assert "latent_liquidity" in components
    assert "non_linear" in components
    assert "order_book_clustering" in components
    assert "quantum_echo" in components
    assert "tactical_liquidity_bifurcation" in components
    assert "execution_diffusion_contraction" in components
    assert "resiliency" in components


def test_composite_alpha_with_sample_data():
    """Test composite alpha with some sample input data."""
    data = {
        'apb': {},
        'gap_amplification': {},
        'llrti': {},
        'non_linear': {},
        'order_book': {},
        'qle': {},
        'tactical_liquidity': {},
        'edch': {},
        'resiliency': {},
    }
    result = composite_alpha_node(data)
    components = result["components"]
    expected = sum(components.values()) / len(components)
    assert result["alpha"] == expected
    assert len(components) == 9
