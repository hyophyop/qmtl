from __future__ import annotations

from pathlib import Path
import importlib.resources as resources


_EXAMPLES_PKG = "qmtl.examples"


def create_project(path: Path) -> None:
    """Create a new project scaffold under *path*."""
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
    (dest / "strategy.py").write_bytes(
        examples.joinpath("general_strategy.py").read_bytes()
    )


__all__ = ["create_project"]
