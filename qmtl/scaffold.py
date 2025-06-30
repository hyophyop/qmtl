from __future__ import annotations

from pathlib import Path
import shutil

_EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def create_project(path: Path) -> None:
    """Create a new project scaffold under *path*."""
    dest = Path(path)
    dest.mkdir(parents=True, exist_ok=True)

    shutil.copy(_EXAMPLES_DIR / "qmtl.yml", dest / "qmtl.yml")
    shutil.copy(_EXAMPLES_DIR / "general_strategy.py", dest / "strategy.py")


__all__ = ["create_project"]
