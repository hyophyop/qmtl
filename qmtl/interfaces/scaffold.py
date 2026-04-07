from __future__ import annotations

import importlib.resources as resources
from pathlib import Path
from typing import cast

from .config_templates import write_template
from .project_templates import (
    DEFAULT_ENV_EXAMPLE,
    DEFAULT_QMTL_CONFIG,
    DEFAULT_STRATEGY_TEMPLATE,
)

_EXAMPLES_PKG = "qmtl.examples"
_LEGACY_TEMPLATE_ERROR = (
    "Legacy scaffold template selection is no longer supported. "
    "Use the public `qmtl init <path>` scaffold and customize `strategies/my_strategy.py`."
)


def _examples_root() -> Path:
    """Return the examples package as a concrete filesystem path."""

    return cast(Path, resources.files(_EXAMPLES_PKG))


def create_public_project(path: Path, *, config_profile: str = "minimal") -> None:
    """Create the blessed strategy-author scaffold used by ``qmtl init``."""

    dest = Path(path)
    dest.mkdir(parents=True, exist_ok=True)

    strategies_dir = dest / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)
    (strategies_dir / "__init__.py").write_text("")
    (strategies_dir / "my_strategy.py").write_text(DEFAULT_STRATEGY_TEMPLATE)
    (dest / ".env.example").write_text(DEFAULT_ENV_EXAMPLE)

    if config_profile == "minimal":
        (dest / "qmtl.yml").write_text(DEFAULT_QMTL_CONFIG)
    else:
        write_template(config_profile, dest / "qmtl.yml", force=True)


def copy_docs(dest: Path) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    examples = _examples_root()
    docs_src = examples.joinpath("docs")
    docs_dest = dest / "docs"
    if docs_src.is_dir():
        for file in docs_src.rglob("*"):
            if file.is_file():
                dst_file = docs_dest / file.relative_to(docs_src)
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                dst_file.write_bytes(file.read_bytes())


def copy_scripts(dest: Path) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    examples = _examples_root()
    scripts_src = examples.joinpath("scripts")
    scripts_dest = dest / "scripts"
    if scripts_src.is_dir():
        for file in scripts_src.rglob("*"):
            if file.is_file():
                dst_file = scripts_dest / file.relative_to(scripts_src)
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                dst_file.write_bytes(file.read_bytes())


def copy_sample_data(dest: Path) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    examples = _examples_root()
    data_dir = dest / "data"
    data_dir.mkdir(exist_ok=True)
    sample = examples.joinpath("data/sample_ohlcv.csv")
    if sample.is_file():
        (data_dir / "sample_ohlcv.csv").write_bytes(sample.read_bytes())
    nb_src = examples.joinpath("notebooks/strategy_analysis_example.ipynb")
    if nb_src.is_file():
        nb_dest = dest / "notebooks"
        nb_dest.mkdir(exist_ok=True)
        (nb_dest / "strategy_analysis_example.ipynb").write_bytes(
            nb_src.read_bytes()
        )


def copy_pyproject(dest: Path) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    examples = _examples_root()
    py_src = examples.joinpath("pyproject.toml")
    if py_src.is_file():
        (dest / "pyproject.toml").write_bytes(py_src.read_bytes())


def create_project(
    path: Path,
    template: str = "general",
    with_sample_data: bool = False,
    with_docs: bool = False,
    with_scripts: bool = False,
    with_pyproject: bool = False,
    *,
    config_profile: str = "minimal",
) -> None:
    """Compatibility wrapper around the public ``qmtl init`` scaffold.

    The repository now maintains a single blessed project layout centered on
    ``strategies/my_strategy.py``. Optional sample/docs/script assets remain
    available here for compatibility with older tests and tooling.
    """

    if template != "general":
        raise ValueError(_LEGACY_TEMPLATE_ERROR)

    dest = Path(path)
    create_public_project(dest, config_profile=config_profile)
    if with_docs:
        copy_docs(dest)
    if with_scripts:
        copy_scripts(dest)
    if with_sample_data:
        copy_sample_data(dest)
    if with_pyproject:
        copy_pyproject(dest)


__all__ = [
    "create_project",
    "create_public_project",
    "copy_docs",
    "copy_scripts",
    "copy_sample_data",
    "copy_pyproject",
]
