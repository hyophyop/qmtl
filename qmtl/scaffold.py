from __future__ import annotations

from pathlib import Path
import importlib.resources as resources


_EXAMPLES_PKG = "qmtl.examples"

# Mapping of template names to example files relative to ``qmtl.examples``
TEMPLATES = {
    "general": "general_strategy.py",
    "single_indicator": "templates/single_indicator.py",
    "multi_indicator": "templates/multi_indicator.py",
    "branching": "templates/branching.py",
    "state_machine": "templates/state_machine.py",
}


def create_project(path: Path, template: str = "general") -> None:
    """Create a new project scaffold under *path* using the given *template*."""
    dest = Path(path)
    dest.mkdir(parents=True, exist_ok=True)

    # extension package directories
    for sub in ["generators", "indicators", "transforms"]:
        pkg = dest / sub
        pkg.mkdir(exist_ok=True)
        (pkg / "__init__.py").touch()

    examples = resources.files(_EXAMPLES_PKG)
    (dest / "qmtl.yml").write_bytes(
        examples.joinpath("qmtl.yml").read_bytes()
    )
    try:
        template_file = TEMPLATES[template]
    except KeyError:
        raise ValueError(f"unknown template: {template}")

    (dest / "strategy.py").write_bytes(
        examples.joinpath(template_file).read_bytes()
    )


__all__ = ["create_project", "TEMPLATES"]
