"""List available strategy layers."""

from __future__ import annotations

import argparse

from ..layers import Layer, load_layer_metadata
from qmtl.utils.i18n import _


def run(argv: list[str] | None = None) -> None:
    """Entry point for the ``list-layers`` subcommand."""

    parser = argparse.ArgumentParser(
        prog="qmtl project list-layers",
        description=_("List available layers and their metadata"),
    )
    parser.add_argument(
        "--show-templates",
        action="store_true",
        help=_("Include template names for each layer"),
    )
    parser.add_argument(
        "--show-requires",
        action="store_true",
        help=_("Include dependency information for templates"),
    )
    args = parser.parse_args(argv)

    print(_("Available layers:"))
    for layer in Layer:
        metadata = load_layer_metadata(layer)
        print(_("  {value:12} - {desc}").format(value=layer.value, desc=metadata.description))
        if args.show_templates and metadata.templates:
            for template in metadata.templates:
                requires = ""
                if args.show_requires and template.requires:
                    requires = _(" (requires: {req})").format(req=', '.join(template.requires))
                print(_("    • {name}{req} - {desc}").format(name=template.name, req=requires, desc=template.description))
