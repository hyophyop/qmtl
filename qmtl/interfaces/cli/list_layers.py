"""List available strategy layers."""

from __future__ import annotations

import argparse

from ..layers import Layer, load_layer_metadata


def run(argv: list[str] | None = None) -> None:
    """Entry point for the ``list-layers`` subcommand."""

    parser = argparse.ArgumentParser(
        prog="qmtl project list-layers",
        description="List available layers and their metadata",
    )
    parser.add_argument(
        "--show-templates",
        action="store_true",
        help="Include template names for each layer",
    )
    parser.add_argument(
        "--show-requires",
        action="store_true",
        help="Include dependency information for templates",
    )
    args = parser.parse_args(argv)

    print("Available layers:")
    for layer in Layer:
        metadata = load_layer_metadata(layer)
        print(f"  {layer.value:12} - {metadata.description}")
        if args.show_templates and metadata.templates:
            for template in metadata.templates:
                requires = ""
                if args.show_requires and template.requires:
                    requires = f" (requires: {', '.join(template.requires)})"
                print(f"    • {template.name}{requires} - {template.description}")
