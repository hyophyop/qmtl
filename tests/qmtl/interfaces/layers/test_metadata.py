"""Tests for layer metadata and validation."""

from __future__ import annotations

from qmtl.interfaces.layers import (
    Layer,
    LayerValidator,
    load_layer_metadata,
    get_layer_dependencies,
    get_transitive_dependencies,
)


def test_layer_enum():
    """Test that all expected layers are defined."""
    assert Layer.DATA == "data"
    assert Layer.SIGNAL == "signal"
    assert Layer.EXECUTION == "execution"
    assert Layer.BROKERAGE == "brokerage"
    assert Layer.MONITORING == "monitoring"


def test_layer_dependencies():
    """Test layer dependency graph."""
    assert get_layer_dependencies(Layer.DATA) == []
    assert get_layer_dependencies(Layer.SIGNAL) == [Layer.DATA]
    assert get_layer_dependencies(Layer.EXECUTION) == [Layer.SIGNAL]
    assert get_layer_dependencies(Layer.BROKERAGE) == [Layer.EXECUTION]
    assert get_layer_dependencies(Layer.MONITORING) == []


def test_transitive_dependencies():
    """Test transitive dependency resolution."""
    # BROKERAGE depends on EXECUTION -> SIGNAL -> DATA
    deps = get_transitive_dependencies(Layer.BROKERAGE)
    assert Layer.DATA in deps
    assert Layer.SIGNAL in deps
    assert Layer.EXECUTION in deps
    assert Layer.BROKERAGE not in deps  # Should not include self

    # DATA has no dependencies
    deps = get_transitive_dependencies(Layer.DATA)
    assert len(deps) == 0

    # MONITORING is independent
    deps = get_transitive_dependencies(Layer.MONITORING)
    assert len(deps) == 0


def test_load_layer_metadata():
    """Test loading layer metadata."""
    metadata = load_layer_metadata(Layer.DATA)
    assert metadata.layer == Layer.DATA
    assert metadata.description
    assert len(metadata.provides) > 0
    assert len(metadata.templates) > 0


class TestLayerValidator:
    """Tests for LayerValidator."""

    def test_validate_valid_combination(self):
        """Test validation of valid layer combination."""
        validator = LayerValidator()
        result = validator.validate_layers([Layer.DATA, Layer.SIGNAL])
        assert result.valid
        assert len(result.errors) == 0

    def test_validate_missing_dependencies(self):
        """Test validation fails when dependencies are missing."""
        validator = LayerValidator()
        # SIGNAL requires DATA
        result = validator.validate_layers([Layer.SIGNAL])
        assert not result.valid
        assert len(result.errors) > 0
        assert "DATA" in str(result.errors) or "data" in str(result.errors)

    def test_validate_duplicate_layers(self):
        """Test validation fails with duplicate layers."""
        validator = LayerValidator()
        result = validator.validate_layers([Layer.DATA, Layer.DATA])
        assert not result.valid
        assert "duplicate" in str(result.errors).lower()

    def test_validate_complex_pipeline(self):
        """Test validation of complete pipeline."""
        validator = LayerValidator()
        result = validator.validate_layers([
            Layer.DATA,
            Layer.SIGNAL,
            Layer.EXECUTION,
            Layer.BROKERAGE,
            Layer.MONITORING,
        ])
        assert result.valid

    def test_validate_add_layer_valid(self):
        """Test adding a valid layer."""
        validator = LayerValidator()
        result = validator.validate_add_layer(
            existing_layers=[Layer.DATA],
            new_layer=Layer.SIGNAL,
        )
        assert result.valid

    def test_validate_add_layer_duplicate(self):
        """Test adding duplicate layer fails."""
        validator = LayerValidator()
        result = validator.validate_add_layer(
            existing_layers=[Layer.DATA, Layer.SIGNAL],
            new_layer=Layer.SIGNAL,
        )
        assert not result.valid
        assert "already exists" in str(result.errors).lower()

    def test_validate_add_layer_missing_deps(self):
        """Test adding layer with missing dependencies fails."""
        validator = LayerValidator()
        result = validator.validate_add_layer(
            existing_layers=[Layer.DATA],
            new_layer=Layer.EXECUTION,  # Requires SIGNAL
        )
        assert not result.valid
        assert "signal" in str(result.errors).lower()

    def test_get_minimal_layer_set(self):
        """Test minimal layer set includes all dependencies."""
        validator = LayerValidator()
        result = validator.get_minimal_layer_set([Layer.EXECUTION])
        
        # Should include DATA, SIGNAL, EXECUTION (in that order)
        assert Layer.DATA in result
        assert Layer.SIGNAL in result
        assert Layer.EXECUTION in result
        
        # Should be in dependency order
        assert result.index(Layer.DATA) < result.index(Layer.SIGNAL)
        assert result.index(Layer.SIGNAL) < result.index(Layer.EXECUTION)

    def test_topological_sort(self):
        """Test dependency ordering."""
        validator = LayerValidator()
        layers = [Layer.EXECUTION, Layer.DATA, Layer.SIGNAL]
        sorted_layers = validator._topological_sort(layers)
        
        # DATA should come first, then SIGNAL, then EXECUTION
        assert sorted_layers.index(Layer.DATA) < sorted_layers.index(Layer.SIGNAL)
        assert sorted_layers.index(Layer.SIGNAL) < sorted_layers.index(Layer.EXECUTION)

    def test_suggest_layers_for_backtest(self):
        """Test layer suggestions for backtesting."""
        validator = LayerValidator()
        layers = validator.suggest_layers_for_use_case("backtest")
        assert Layer.DATA in layers
        assert Layer.SIGNAL in layers
        assert len(layers) == 2

    def test_suggest_layers_for_production(self):
        """Test layer suggestions for production."""
        validator = LayerValidator()
        layers = validator.suggest_layers_for_use_case("production")
        assert Layer.DATA in layers
        assert Layer.SIGNAL in layers
        assert Layer.EXECUTION in layers
        assert Layer.BROKERAGE in layers
        assert Layer.MONITORING in layers

    def test_suggest_layers_for_research(self):
        """Test layer suggestions for research."""
        validator = LayerValidator()
        layers = validator.suggest_layers_for_use_case("research")
        assert Layer.DATA in layers
        assert Layer.SIGNAL in layers
        assert Layer.MONITORING in layers
