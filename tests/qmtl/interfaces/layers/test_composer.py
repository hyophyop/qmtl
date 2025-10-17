"""Tests for LayerComposer."""

from __future__ import annotations

from pathlib import Path

import pytest

from qmtl.interfaces.layers import Layer, LayerComposer


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project_dir = tmp_path / "test_project"
    return project_dir


class TestLayerComposer:
    """Tests for LayerComposer."""

    def test_compose_minimal_project(self, temp_project: Path):
        """Test creating a minimal project."""
        composer = LayerComposer()
        result = composer.compose(
            layers=[Layer.DATA, Layer.SIGNAL],
            dest=temp_project,
        )

        assert result.valid
        assert temp_project.exists()
        assert (temp_project / "layers").exists()
        assert (temp_project / "layers" / "data").exists()
        assert (temp_project / "layers" / "signal").exists()
        assert (temp_project / "strategy.py").exists()
        assert (temp_project / "qmtl.yml").exists()
        assert (temp_project / ".gitignore").exists()
        assert (temp_project / "tests").exists()

    def test_compose_with_monitoring(self, temp_project: Path):
        """Test creating project with monitoring layer."""
        composer = LayerComposer()
        result = composer.compose(
            layers=[Layer.DATA, Layer.SIGNAL, Layer.MONITORING],
            dest=temp_project,
        )

        assert result.valid
        assert (temp_project / "layers" / "monitoring").exists()

    def test_compose_full_pipeline(self, temp_project: Path):
        """Test creating project with full pipeline."""
        composer = LayerComposer()
        result = composer.compose(
            layers=[
                Layer.DATA,
                Layer.SIGNAL,
                Layer.EXECUTION,
                Layer.BROKERAGE,
                Layer.MONITORING,
            ],
            dest=temp_project,
        )

        assert result.valid
        for layer in [Layer.DATA, Layer.SIGNAL, Layer.EXECUTION, Layer.BROKERAGE, Layer.MONITORING]:
            assert (temp_project / "layers" / layer.value).exists()

    def test_compose_fails_missing_dependencies(self, temp_project: Path):
        """Test that composition fails with missing dependencies."""
        composer = LayerComposer()
        result = composer.compose(
            layers=[Layer.SIGNAL],  # Missing DATA dependency
            dest=temp_project,
        )

        assert not result.valid
        assert len(result.errors) > 0

    def test_compose_fails_duplicate_layers(self, temp_project: Path):
        """Test that composition fails with duplicate layers."""
        composer = LayerComposer()
        result = composer.compose(
            layers=[Layer.DATA, Layer.DATA],
            dest=temp_project,
        )

        assert not result.valid
        assert "duplicate" in str(result.errors).lower()

    def test_compose_fails_existing_directory(self, temp_project: Path):
        """Test that composition fails if directory exists without force."""
        temp_project.mkdir(parents=True)
        (temp_project / "dummy.txt").write_text("exists")

        composer = LayerComposer()
        result = composer.compose(
            layers=[Layer.DATA, Layer.SIGNAL],
            dest=temp_project,
            force=False,
        )

        assert not result.valid
        assert "already exists" in str(result.errors).lower()

    def test_compose_with_force_overwrites(self, temp_project: Path):
        """Test that force flag allows overwriting."""
        temp_project.mkdir(parents=True)
        (temp_project / "dummy.txt").write_text("exists")

        composer = LayerComposer()
        result = composer.compose(
            layers=[Layer.DATA, Layer.SIGNAL],
            dest=temp_project,
            force=True,
        )

        assert result.valid
        assert (temp_project / "layers").exists()

    def test_add_layer_to_existing_project(self, temp_project: Path):
        """Test adding a layer to an existing project."""
        # First create a minimal project
        composer = LayerComposer()
        composer.compose(
            layers=[Layer.DATA, Layer.SIGNAL],
            dest=temp_project,
        )

        # Then add monitoring
        result = composer.add_layer(
            dest=temp_project,
            layer=Layer.MONITORING,
        )

        assert result.valid
        assert (temp_project / "layers" / "monitoring").exists()

    def test_add_layer_fails_duplicate(self, temp_project: Path):
        """Test that adding duplicate layer fails."""
        composer = LayerComposer()
        composer.compose(
            layers=[Layer.DATA, Layer.SIGNAL],
            dest=temp_project,
        )

        # Try to add DATA again
        result = composer.add_layer(
            dest=temp_project,
            layer=Layer.DATA,
            force=False,
        )

        assert not result.valid
        assert "already exists" in str(result.errors).lower()

    def test_add_layer_with_force_allows_duplicate(self, temp_project: Path):
        """Test that force flag allows re-adding layer."""
        composer = LayerComposer()
        composer.compose(
            layers=[Layer.DATA, Layer.SIGNAL],
            dest=temp_project,
        )

        # Add DATA again with force
        result = composer.add_layer(
            dest=temp_project,
            layer=Layer.DATA,
            force=True,
        )

        assert result.valid

    def test_add_layer_force_requires_dependencies(self, temp_project: Path):
        """Force overwrite should still enforce dependency validation."""
        composer = LayerComposer()
        composer.compose(
            layers=[Layer.DATA],
            dest=temp_project,
        )

        result = composer.add_layer(
            dest=temp_project,
            layer=Layer.BROKERAGE,
            force=True,
        )

        assert not result.valid
        assert "execution" in str(result.errors).lower()

    def test_add_layer_fails_missing_dependencies(self, temp_project: Path):
        """Test that adding layer with missing dependencies fails."""
        composer = LayerComposer()
        composer.compose(
            layers=[Layer.DATA],
            dest=temp_project,
        )

        # Try to add EXECUTION without SIGNAL
        result = composer.add_layer(
            dest=temp_project,
            layer=Layer.EXECUTION,
        )

        assert not result.valid
        assert "signal" in str(result.errors).lower()

    def test_add_layer_fails_nonexistent_project(self, temp_project: Path):
        """Test that adding layer to nonexistent project fails."""
        composer = LayerComposer()
        result = composer.add_layer(
            dest=temp_project,
            layer=Layer.DATA,
        )

        assert not result.valid
        assert "does not exist" in str(result.errors).lower()

    def test_validate_project_valid(self, temp_project: Path):
        """Test validation of valid project."""
        composer = LayerComposer()
        composer.compose(
            layers=[Layer.DATA, Layer.SIGNAL],
            dest=temp_project,
        )

        result = composer.validate_project(temp_project)
        assert result.valid

    def test_validate_project_nonexistent(self, temp_project: Path):
        """Test validation of nonexistent project."""
        composer = LayerComposer()
        result = composer.validate_project(temp_project)

        assert not result.valid
        assert "does not exist" in str(result.errors).lower()

    def test_validate_project_no_layers(self, temp_project: Path):
        """Test validation of project without layers."""
        temp_project.mkdir(parents=True)
        composer = LayerComposer()
        result = composer.validate_project(temp_project)

        assert not result.valid
        assert "no layers" in str(result.errors).lower()

    def test_detect_existing_layers(self, temp_project: Path):
        """Test detection of existing layers."""
        composer = LayerComposer()
        composer.compose(
            layers=[Layer.DATA, Layer.SIGNAL, Layer.MONITORING],
            dest=temp_project,
        )

        detected = composer._detect_existing_layers(temp_project)
        assert Layer.DATA in detected
        assert Layer.SIGNAL in detected
        assert Layer.MONITORING in detected
        assert len(detected) == 3

    def test_create_base_structure(self, temp_project: Path):
        """Test creation of base project structure."""
        composer = LayerComposer()
        composer._create_base_structure(temp_project)

        assert (temp_project / "layers").exists()
        assert (temp_project / "layers" / "__init__.py").exists()
        assert (temp_project / "strategy.py").exists()
        assert (temp_project / "qmtl.yml").exists()
        assert (temp_project / ".gitignore").exists()
        assert (temp_project / "tests").exists()
        assert (temp_project / "tests" / "test_strategy.py").exists()

        # Check content
        strategy_content = (temp_project / "strategy.py").read_text()
        assert "def main()" in strategy_content
        
        qmtl_content = (temp_project / "qmtl.yml").read_text()
        assert "gateway:" in qmtl_content
        assert "dagmanager:" in qmtl_content
