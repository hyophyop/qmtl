"""Layer composer for building projects from layers."""

from __future__ import annotations

import importlib.resources as resources
from pathlib import Path
from typing import Dict, List, Optional

from .metadata import Layer, load_layer_metadata
from .validator import LayerValidator, ValidationResult


class LayerComposer:
    """Composes layers into a project structure."""

    def __init__(self, validator: Optional[LayerValidator] = None):
        """Initialize composer.

        Args:
            validator: Layer validator instance. Creates default if None.
        """
        self.validator = validator or LayerValidator()

    def compose(
        self,
        layers: List[Layer],
        dest: Path,
        *,
        template_choices: Optional[Dict[Layer, str]] = None,
        force: bool = False,
    ) -> ValidationResult:
        """Compose layers into a project at dest.

        Args:
            layers: List of layers to include
            dest: Destination directory
            template_choices: Optional mapping of layer to template name
            force: Force overwrite if destination exists

        Returns:
            ValidationResult indicating success or failure
        """
        dest = Path(dest)

        # Validate layers
        validation = self.validator.validate_layers(layers)
        if not validation.valid:
            return validation

        # Check destination
        if dest.exists() and not force:
            return ValidationResult(
                valid=False,
                errors=[f"Destination '{dest}' already exists. Use --force to overwrite."],
            )

        # Create directory structure
        dest.mkdir(parents=True, exist_ok=True)

        # Create base structure
        self._create_base_structure(dest)

        # Add each layer
        template_choices = template_choices or {}
        for layer in layers:
            template_name = template_choices.get(layer)
            self._add_layer_to_project(dest, layer, template_name)

        return ValidationResult(valid=True)

    def add_layer(
        self,
        dest: Path,
        layer: Layer,
        *,
        template_name: Optional[str] = None,
        force: bool = False,
    ) -> ValidationResult:
        """Add a layer to an existing project.

        Args:
            dest: Existing project directory
            layer: Layer to add
            template_name: Specific template to use (uses default if None)
            force: Force overwrite if layer already exists

        Returns:
            ValidationResult indicating success or failure
        """
        dest = Path(dest)

        # Check if project exists
        if not dest.exists():
            return ValidationResult(
                valid=False,
                errors=[f"Project directory '{dest}' does not exist."],
            )

        # Detect existing layers
        existing_layers = self._detect_existing_layers(dest)

        # Validate addition
        validation = self.validator.validate_add_layer(existing_layers, layer)
        if not validation.valid:
            if force and layer in existing_layers:
                # Ignore duplicate-layer conflicts but still enforce dependency checks
                dependency_validation = self.validator.validate_add_layer(
                    [existing for existing in existing_layers if existing != layer],
                    layer,
                )

                if not dependency_validation.valid:
                    return dependency_validation
            else:
                return validation

        # Add the layer
        self._add_layer_to_project(dest, layer, template_name)

        return ValidationResult(valid=True)

    def validate_project(self, dest: Path) -> ValidationResult:
        """Validate an existing project structure.

        Args:
            dest: Project directory to validate

        Returns:
            ValidationResult with any issues found
        """
        dest = Path(dest)

        if not dest.exists():
            return ValidationResult(
                valid=False,
                errors=[f"Project directory '{dest}' does not exist."],
            )

        # Detect existing layers
        existing_layers = self._detect_existing_layers(dest)

        if not existing_layers:
            return ValidationResult(
                valid=False,
                errors=["No layers detected in project."],
            )

        # Validate layer combination
        return self.validator.validate_layers(existing_layers)

    def _create_base_structure(self, dest: Path) -> None:
        """Create base project structure.

        Creates:
        - layers/ directory
        - strategy.py entry point
        - qmtl.yml config
        - tests/ directory
        """
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)

        # Create directories
        (dest / "layers").mkdir(exist_ok=True)
        (dest / "tests").mkdir(exist_ok=True)

        # Create __init__.py files
        (dest / "layers" / "__init__.py").write_text(
            '"""Project layers."""\n'
        )

        # Create basic strategy.py
        strategy_template = '''"""Strategy execution entry point."""

from __future__ import annotations

from qmtl.runtime.sdk import Runner

try:
    from layers.signal.strategy import create_strategy  # type: ignore
except ImportError as exc:  # pragma: no cover - exercised via integration tests
    def create_strategy():
        """Fallback when no signal layer is scaffolded."""
        raise NotImplementedError(
            "Signal layer not available. Add a signal layer or implement "
            "create_strategy() in strategy.py."
        ) from exc


def main() -> None:
    """Run the strategy."""
    strategy = create_strategy()

    # Run in offline mode (no Gateway/WorldService)
    # For production, use: Runner.run(strategy, world_id=\"...\", gateway_url=\"...\")
    result = Runner.offline(strategy)
    print("Strategy execution completed")
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
'''
        (dest / "strategy.py").write_text(strategy_template)

        # Create basic qmtl.yml (will be enhanced by layers)
        qmtl_config = """# QMTL Configuration
# See docs/reference/configuration.md for details

worldservice:
  url: http://localhost:8080
  timeout: 0.3
  retries: 2

gateway:
  host: 0.0.0.0
  port: 8000
  redis_dsn: redis://localhost:6379
  database_backend: sqlite
  database_dsn: ./qmtl.db

dagmanager:
  memory_repo_path: memrepo.gpickle
  neo4j_dsn: bolt://localhost:7687
  kafka_dsn: localhost:9092
  grpc_host: 0.0.0.0
  grpc_port: 50051
"""
        (dest / "qmtl.yml").write_text(qmtl_config)

        # Create .gitignore
        gitignore = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/

# QMTL
*.db
data/*.csv
!data/sample*.csv

# IDE
.vscode/
.idea/
*.swp
*.swo
"""
        (dest / ".gitignore").write_text(gitignore)

        # Create basic test
        test_template = '''"""Basic strategy tests."""

import pytest


def test_strategy_import():
    """Test that strategy can be imported when a signal layer exists."""
    try:
        from layers.signal.strategy import create_strategy
    except ImportError:
        pytest.skip("Signal layer not scaffolded")
    assert create_strategy is not None
'''
        (dest / "tests" / "test_strategy.py").write_text(test_template)

    def _add_layer_to_project(
        self, dest: Path, layer: Layer, template_name: Optional[str] = None
    ) -> None:
        """Add a specific layer to the project.

        Args:
            dest: Project directory
            layer: Layer to add
            template_name: Specific template to use (uses first if None)
        """
        dest = Path(dest)
        layer_dir = dest / "layers" / layer.value
        layer_dir.mkdir(parents=True, exist_ok=True)

        # Create __init__.py
        (layer_dir / "__init__.py").write_text(
            f'"""{layer.value.capitalize()} layer components."""\n'
        )

        # Load layer metadata to get templates
        metadata = load_layer_metadata(layer)

        # Choose template
        if template_name:
            template_info = next(
                (t for t in metadata.templates if t.name == template_name), None
            )
            if not template_info:
                # Use first template as fallback
                template_info = metadata.templates[0] if metadata.templates else None
        else:
            template_info = metadata.templates[0] if metadata.templates else None

        if template_info:
            # Copy template file
            self._copy_layer_template(layer, template_info.file, layer_dir)

    def _copy_layer_template(
        self, layer: Layer, template_file: str, dest_dir: Path
    ) -> None:
        """Copy a template file to the destination.

        Args:
            layer: Layer type
            template_file: Template filename
            dest_dir: Destination directory
        """
        # For now, create placeholder files
        # In full implementation, this would copy from qmtl/examples/templates/layers/
        try:
            # Try to load from package resources
            examples = resources.files("qmtl.examples")
            template_path = examples.joinpath("templates", "layers", layer.value, template_file)
            
            if template_path.is_file():
                dest_file = dest_dir / template_file
                dest_file.write_bytes(template_path.read_bytes())
            else:
                # Create placeholder if template doesn't exist yet
                self._create_placeholder_template(layer, template_file, dest_dir)
        except Exception:
            # Fallback to placeholder
            self._create_placeholder_template(layer, template_file, dest_dir)

    def _create_placeholder_template(
        self, layer: Layer, template_file: str, dest_dir: Path
    ) -> None:
        """Create a placeholder template file.

        Args:
            layer: Layer type
            template_file: Template filename
            dest_dir: Destination directory
        """
        dest_file = dest_dir / template_file
        
        placeholder = f'''"""Placeholder for {layer.value} layer.

TODO: Implement {layer.value} logic here.
"""

from __future__ import annotations


def create_{layer.value}():
    """Create {layer.value} component."""
    raise NotImplementedError("TODO: Implement {layer.value} component")
'''
        dest_file.write_text(placeholder)

    def _detect_existing_layers(self, dest: Path) -> List[Layer]:
        """Detect which layers exist in a project.

        Args:
            dest: Project directory

        Returns:
            List of detected layers
        """
        dest = Path(dest)
        layers_dir = dest / "layers"

        if not layers_dir.exists():
            return []

        detected = []
        for layer in Layer:
            layer_dir = layers_dir / layer.value
            if layer_dir.exists() and layer_dir.is_dir():
                detected.append(layer)

        return detected
