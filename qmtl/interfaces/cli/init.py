from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from ..scaffold import (
    TEMPLATES,
    copy_docs,
    copy_pyproject,
    copy_sample_data,
    copy_scripts,
    create_project,
)
from ..layers import Layer, LayerComposer, PresetLoader, LayerValidator
from ..config_templates import available_profiles


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``init`` subcommand."""

    parser = argparse.ArgumentParser(
        prog="qmtl project init",
        description="Initialize new project (see docs/guides/strategy_workflow.md)",
    )
    parser.epilog = "More docs: docs/reference/templates.md"
    parser.add_argument(
        "--path",
        help="Project directory to create scaffolding",
    )

    # Preset/layer options (new system)
    parser.add_argument(
        "--preset",
        help="Preset configuration to use (see docs/architecture/layered_template_system.md)",
    )
    parser.add_argument(
        "--layers",
        help="Comma-separated list of layers to include (e.g., data,signal)",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List available presets and exit",
    )
    parser.add_argument(
        "--list-layers",
        action="store_true",
        help="List available layers and exit",
    )

    # Legacy options (deprecated)
    parser.add_argument(
        "--strategy",
        help="(Deprecated: use --preset) Strategy template to use",
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="(Deprecated: use --list-presets) List available templates and exit",
    )

    # Additional options
    parser.add_argument(
        "--with-sample-data",
        action="store_true",
        help="Include sample OHLCV CSV and notebook",
    )
    parser.add_argument("--with-docs", action="store_true", help="Include docs/ directory template")
    parser.add_argument("--with-scripts", action="store_true", help="Include scripts/ directory template")
    parser.add_argument("--with-pyproject", action="store_true", help="Include pyproject.toml template")
    parser.add_argument("--force", action="store_true", help="Overwrite existing directory")
    parser.add_argument(
        "--config-profile",
        choices=sorted(available_profiles()),
        default="minimal",
        help="Select configuration template for qmtl.yml",
    )

    args = parser.parse_args(argv)

    # Initialize systems
    preset_loader = PresetLoader()
    composer = LayerComposer()
    validator = LayerValidator()

    # Handle list commands
    if args.list_presets or args.list_templates:
        if args.list_templates:
            print(
                "Warning: --list-templates is deprecated, use --list-presets instead",
                file=sys.stderr,
            )
            print("Available templates:")
            for template_name in sorted(TEMPLATES):
                print(template_name)
        if args.list_presets:
            print("Available presets:")
        for preset_name in preset_loader.list_presets():
            preset = preset_loader.get_preset(preset_name)
            if preset:
                print(f"  {preset_name:15} - {preset.description}")
        return

    if args.list_layers:
        print("Available layers:")
        for layer in Layer:
            print(f"  {layer.value:15} - {layer.name}")
        return

    # Check that --path is provided for actual project creation
    if not args.path:
        parser.error("the following arguments are required: --path")

    # Determine if using new layer system or legacy
    use_legacy = False

    if args.strategy:
        print(
            "Warning: --strategy is deprecated, use --preset instead",
            file=sys.stderr,
        )
        use_legacy = True

    # Use legacy system when no layer/preset selection is provided
    if use_legacy or (not args.preset and not args.layers):
        _run_legacy(args)
        return

    # Use new layer system
    if args.preset:
        _run_with_preset(args, preset_loader, composer)
    else:
        _run_with_layers(args, composer, validator)


def _apply_optional_components(dest: Path, args: argparse.Namespace) -> None:
    """Apply optional scaffold pieces that are shared across init flows."""
    if args.with_sample_data:
        copy_sample_data(dest)
    if args.with_docs:
        copy_docs(dest)
    if args.with_scripts:
        copy_scripts(dest)
    if args.with_pyproject:
        copy_pyproject(dest)


def _run_legacy(args) -> None:
    """Run using legacy template system."""
    create_project(
        Path(args.path),
        template=args.strategy or "general",
        with_sample_data=args.with_sample_data,
        with_docs=args.with_docs,
        with_scripts=args.with_scripts,
        with_pyproject=args.with_pyproject,
        config_profile=args.config_profile,
    )
    print(f"Project created at {args.path} using legacy template '{args.strategy or 'general'}'")


def _run_with_preset(args, preset_loader: PresetLoader, composer: LayerComposer) -> None:
    """Run using preset configuration."""
    preset = preset_loader.get_preset(args.preset)
    if not preset:
        print(f"Error: Unknown preset '{args.preset}'")
        print("\nAvailable presets:")
        for name in preset_loader.list_presets():
            p = preset_loader.get_preset(name)
            if p:
                print(f"  {name:15} - {p.description}")
        raise SystemExit(1)

    # Compose project from preset
    result = composer.compose(
        layers=preset.layers,
        dest=Path(args.path),
        template_choices=preset.template_choices,
        force=args.force,
        config_profile=args.config_profile,
    )

    if not result.valid:
        print(f"Error creating project:")
        for error in result.errors:
            print(f"  - {error}")
        raise SystemExit(1)

    print(f"Project created at {args.path} using preset '{preset.name}'")
    print(f"Layers included: {', '.join(layer.value for layer in preset.layers)}")
    _apply_optional_components(Path(args.path), args)


def _run_with_layers(args, composer: LayerComposer, validator: LayerValidator) -> None:
    """Run with explicit layer selection."""
    layer_names = [name.strip() for name in args.layers.split(",")]
    
    try:
        layers = [Layer(name) for name in layer_names]
    except ValueError as e:
        print(f"Error: Invalid layer name - {e}")
        print("\nAvailable layers:")
        for layer in Layer:
            print(f"  {layer.value}")
        raise SystemExit(1)

    # Get minimal layer set with dependencies
    layers = validator.get_minimal_layer_set(layers)

    # Compose project
    result = composer.compose(
        layers=layers,
        dest=Path(args.path),
        force=args.force,
        config_profile=args.config_profile,
    )

    if not result.valid:
        print("Error creating project:")
        for error in result.errors:
            print(f"  - {error}")
        raise SystemExit(1)

    print(f"Project created at {args.path}")
    print(f"Layers included: {', '.join(layer.value for layer in layers)}")
    _apply_optional_components(Path(args.path), args)
