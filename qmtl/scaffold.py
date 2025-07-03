from __future__ import annotations

from pathlib import Path
import shutil
import importlib.resources as resources


_EXAMPLES_PKG = "examples"


def create_project(path: Path) -> None:
    """Create a new project scaffold under *path*."""
    dest = Path(path)
    dest.mkdir(parents=True, exist_ok=True)

    # extension package directories
    for sub in ["generators", "indicators", "transforms"]:
        pkg = dest / sub
        pkg.mkdir(exist_ok=True)
        (pkg / "__init__.py").touch()

    examples_dir = resources.files(_EXAMPLES_PKG)
    shutil.copy(examples_dir / "qmtl.yml", dest / "qmtl.yml")
    shutil.copy(examples_dir / "general_strategy.py", dest / "strategy.py")


__all__ = ["create_project"]
