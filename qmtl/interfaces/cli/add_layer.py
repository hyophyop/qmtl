"""Add layer to existing project command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List
from qmtl.utils.i18n import _

from ..layers import Layer, LayerComposer


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``add-layer`` subcommand."""

    parser = argparse.ArgumentParser(
        prog="qmtl project add-layer",
        description=_("Add a layer to an existing project"),
    )
    parser.add_argument(
        "--path",
        default=".",
        help=_("Project directory (default: current directory)"),
    )
    parser.add_argument(
        "layer",
        help=_("Layer to add (data, signal, execution, brokerage, monitoring)"),
    )
    parser.add_argument(
        "--template",
        help=_("Specific template to use for this layer"),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=_("Force overwrite if layer already exists"),
    )

    args = parser.parse_args(argv)

    # Parse layer
    try:
        layer = Layer(args.layer)
    except ValueError:
        print(_("Error: Invalid layer '{layer}'").format(layer=args.layer), file=sys.stderr)
        print(_("\nAvailable layers:"), file=sys.stderr)
        for layer_option in Layer:
            print(_("  {value}").format(value=layer_option.value), file=sys.stderr)
        raise SystemExit(1)

    # Add layer
    composer = LayerComposer()
    result = composer.add_layer(
        dest=Path(args.path),
        layer=layer,
        template_name=args.template,
        force=args.force,
    )

    if not result.valid:
        print(_("Error adding layer:"), file=sys.stderr)
        for error in result.errors:
            print(_("  - {error}").format(error=error), file=sys.stderr)
        raise SystemExit(1)

    print(_("Layer '{name}' added to project at {path}").format(name=layer.value, path=args.path))
    if args.template:
        print(_("Using template: {template}").format(template=args.template))
