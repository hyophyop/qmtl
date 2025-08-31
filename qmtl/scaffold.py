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


def copy_nodes(dest: Path) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    examples = resources.files(_EXAMPLES_PKG)
    nodes_src = examples.joinpath("nodes")
    nodes_dest = dest / "nodes"
    nodes_dest.mkdir(exist_ok=True)
    (nodes_dest / "__init__.py").write_bytes(
        nodes_src.joinpath("__init__.py").read_bytes()
    )
    for sub in ["generators", "indicators", "transforms"]:
        src_dir = nodes_src.joinpath(sub)
        dst_dir = nodes_dest / sub
        dst_dir.mkdir(exist_ok=True)
        for file in src_dir.iterdir():
            if file.suffix == ".py":
                (dst_dir / file.name).write_bytes(file.read_bytes())


def copy_dags(dest: Path, template: str) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    examples = resources.files(_EXAMPLES_PKG)
    dags_src = examples.joinpath("dags")
    dags_dest = dest / "dags"
    if dags_src.is_dir():
        dags_dest.mkdir(exist_ok=True)
        init_file = dags_src / "__init__.py"
        if init_file.is_file():
            (dags_dest / "__init__.py").write_bytes(init_file.read_bytes())
        example_src = dags_src / "example_strategy"
        if example_src.is_dir():
            example_dest = dags_dest / "example_strategy"
            example_dest.mkdir(exist_ok=True)
            for file in example_src.iterdir():
                if file.is_file():
                    (example_dest / file.name).write_bytes(file.read_bytes())
    try:
        template_file = TEMPLATES[template]
    except KeyError:
        raise ValueError(f"unknown template: {template}")
    (dags_dest / "example_strategy.py").write_bytes(
        examples.joinpath(template_file).read_bytes()
    )


def copy_docs(dest: Path) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    examples = resources.files(_EXAMPLES_PKG)
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
    examples = resources.files(_EXAMPLES_PKG)
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
    examples = resources.files(_EXAMPLES_PKG)
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
    examples = resources.files(_EXAMPLES_PKG)
    py_src = examples.joinpath("pyproject.toml")
    if py_src.is_file():
        (dest / "pyproject.toml").write_bytes(py_src.read_bytes())


def copy_base_files(dest: Path) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    examples = resources.files(_EXAMPLES_PKG)
    (dest / "qmtl.yml").write_bytes(examples.joinpath("qmtl.yml").read_bytes())
    (dest / "config.example.yml").write_bytes(
        examples.joinpath("config.example.yml").read_bytes()
    )
    (dest / ".gitignore").write_bytes(
        examples.joinpath("gitignore").read_bytes()
    )
    readme = examples.joinpath("README.md")
    if readme.is_file():
        (dest / "README.md").write_bytes(readme.read_bytes())
    (dest / "strategy.py").write_bytes(
        examples.joinpath("strategy.py").read_bytes()
    )
    tests_src = examples.joinpath("tests")
    tests_dest = dest / "tests"
    if tests_src.is_dir():
        for file in tests_src.rglob("*"):
            if file.is_file():
                dst_file = tests_dest / file.relative_to(tests_src)
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                dst_file.write_bytes(file.read_bytes())


def create_project(
    path: Path,
    template: str = "general",
    with_sample_data: bool = False,
    with_docs: bool = False,
    with_scripts: bool = False,
    with_pyproject: bool = False,
) -> None:
    """Create a new project scaffold under *path*.

    The project is seeded with example nodes, DAGs and tests. Optional
    components such as docs, scripts, sample data and ``pyproject.toml`` are
    included when the respective flags are enabled.
    """

    dest = Path(path)
    dest.mkdir(parents=True, exist_ok=True)

    copy_nodes(dest)
    copy_dags(dest, template)
    copy_base_files(dest)
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
    "copy_nodes",
    "copy_dags",
    "copy_docs",
    "copy_scripts",
    "copy_sample_data",
    "copy_pyproject",
    "copy_base_files",
    "TEMPLATES",
]

