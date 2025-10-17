"""Add layer to existing project command."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from ..layers import Layer, LayerComposer


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``add-layer`` subcommand."""

    parser = argparse.ArgumentParser(
        prog="qmtl project add-layer",
        description="Add a layer to an existing project",
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "layer",
        help="Layer to add (data, signal, execution, brokerage, monitoring)",
    )
    parser.add_argument(
        "--template",
        help="Specific template to use for this layer",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite if layer already exists",
    )

    args = parser.parse_args(argv)

    # Parse layer
    try:
        layer = Layer(args.layer)
    except ValueError:
        print(f"Error: Invalid layer '{args.layer}'")
        print("\nAvailable layers:")
        for layer_option in Layer:
            print(f"  {layer_option.value}")
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
        print("Error adding layer:")
        for error in result.errors:
            print(f"  - {error}")
        raise SystemExit(1)

    print(f"Layer '{layer.value}' added to project at {args.path}")
    if args.template:
        print(f"Using template: {args.template}")
