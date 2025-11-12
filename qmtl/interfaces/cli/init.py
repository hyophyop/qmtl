from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List
from qmtl.utils.i18n import _

from ..scaffold import copy_docs, copy_pyproject, copy_sample_data, copy_scripts, create_project
from ..layers import Layer, LayerComposer, PresetLoader, LayerValidator
from ..config_templates import available_profiles


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``init`` subcommand."""

    parser = argparse.ArgumentParser(
        prog="qmtl project init",
        description=_("Initialize new project (see docs/guides/strategy_workflow.md)"),
    )
    parser.epilog = _("More docs: docs/reference/templates.md")
    parser.add_argument(
        "--path",
        help=_("Project directory to create scaffolding"),
    )

    # Preset/layer options (new system)
    parser.add_argument(
        "--preset",
        help=_("Preset configuration to use (see docs/architecture/layered_template_system.md)"),
    )
    parser.add_argument(
        "--layers",
        help=_("Comma-separated list of layers to include (e.g., data,signal)"),
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help=_("(Deprecated: use 'qmtl project list-presets') List available presets and exit"),
    )
    parser.add_argument(
        "--list-layers",
        action="store_true",
        help=_("(Deprecated: use 'qmtl project list-layers') List available layers and exit"),
    )

    # Legacy options (deprecated)
    parser.add_argument(
        "--strategy",
        help=_("(Deprecated: use --preset) Strategy template to use"),
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help=_("(Deprecated: use --list-presets) List available templates and exit"),
    )

    # Additional options
    parser.add_argument(
        "--with-sample-data",
        action="store_true",
        help=_("Include sample OHLCV CSV and notebook"),
    )
    parser.add_argument("--with-docs", action="store_true", help=_("Include docs/ directory template"))
    parser.add_argument("--with-scripts", action="store_true", help=_("Include scripts/ directory template"))
    parser.add_argument("--with-pyproject", action="store_true", help=_("Include pyproject.toml template"))
    parser.add_argument("--force", action="store_true", help=_("Overwrite existing directory"))
    parser.add_argument(
        "--config-profile",
        choices=sorted(available_profiles()),
        default="minimal",
        help=_("Select configuration template for qmtl.yml"),
    )

    args = parser.parse_args(argv)

    # Initialize systems
    preset_loader = PresetLoader()
    composer = LayerComposer()
    validator = LayerValidator()

    # Handle list commands via dedicated subcommands
    if args.list_templates:
        print(_("Warning: --list-templates is deprecated, use --list-presets instead"), file=sys.stderr)
        from . import presets as presets_cli  # Local import to avoid circular dependency

        presets_cli.run(["--show-legacy-templates"])
        return

    if args.list_presets:
        print(
            _("Warning: --list-presets is deprecated, use 'qmtl project list-presets'"),
            file=sys.stderr,
        )
        from . import presets as presets_cli  # Local import to avoid circular dependency

        presets_cli.run([])
        return

    if args.list_layers:
        print(
            _("Warning: --list-layers is deprecated, use 'qmtl project list-layers'"),
            file=sys.stderr,
        )
        from . import list_layers as list_layers_cli  # Local import to avoid circular dependency

        list_layers_cli.run([])
        return

    # Check that --path is provided for actual project creation
    if not args.path:
        parser.error("the following arguments are required: --path")

    # Determine if using new layer system or legacy
    use_legacy = False

    if args.strategy:
        print(_("Warning: --strategy is deprecated, use --preset instead"), file=sys.stderr)
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
    print(_("Project created at {path} using legacy template '{template}'").format(path=args.path, template=(args.strategy or 'general')))


def _run_with_preset(args, preset_loader: PresetLoader, composer: LayerComposer) -> None:
    """Run using preset configuration."""
    preset = preset_loader.get_preset(args.preset)
    if not preset:
        print(_("Error: Unknown preset '{preset}'").format(preset=args.preset))
        print(_("\nAvailable presets:"))
        for name in preset_loader.list_presets():
            p = preset_loader.get_preset(name)
            if p:
                print(_("  {name:15} - {desc}").format(name=name, desc=p.description))
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
        print(_("Error creating project:"))
        for error in result.errors:
            print(_("  - {error}").format(error=error))
        raise SystemExit(1)

    print(_("Project created at {path} using preset '{preset}'").format(path=args.path, preset=preset.name))
    print(_("Layers included: {layers}").format(layers=', '.join(layer.value for layer in preset.layers)))
    _apply_optional_components(Path(args.path), args)


def _run_with_layers(args, composer: LayerComposer, validator: LayerValidator) -> None:
    """Run with explicit layer selection."""
    layer_names = [name.strip() for name in args.layers.split(",")]
    
    try:
        layers = [Layer(name) for name in layer_names]
    except ValueError as e:
        print(_("Error: Invalid layer name - {error}").format(error=e))
        print(_("\nAvailable layers:"))
        for layer in Layer:
            print(_("  {value}").format(value=layer.value))
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
        print(_("Error creating project:"))
        for error in result.errors:
            print(_("  - {error}").format(error=error))
        raise SystemExit(1)

    print(_("Project created at {path}").format(path=args.path))
    print(_("Layers included: {layers}").format(layers=', '.join(layer.value for layer in layers)))
    _apply_optional_components(Path(args.path), args)
