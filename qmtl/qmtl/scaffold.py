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


def create_project(
    path: Path,
    template: str = "general",
    with_sample_data: bool = False,
    with_docs: bool = False,
    with_scripts: bool = False,
    with_pyproject: bool = False,
) -> None:
    """Create a new project scaffold under *path* using the given *template*.

    Parameters
    ----------
    path:
        Destination directory for the project.
    template:
        Name of example strategy template.
    with_sample_data:
        When ``True`` copy bundled example OHLCV data into ``data/`` of the
        new project.
    with_docs:
        When ``True`` include the ``docs/`` directory template.
    with_scripts:
        When ``True`` include the ``scripts/`` directory template.
    with_pyproject:
        When ``True`` include a ``pyproject.toml`` template.
    """
    dest = Path(path)
    dest.mkdir(parents=True, exist_ok=True)

    examples = resources.files(_EXAMPLES_PKG)

    # extension package directories
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

    # Copy example DAG definitions
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
    (dest / "qmtl.yml").write_bytes(
        examples.joinpath("qmtl.yml").read_bytes()
    )
    (dest / "config.example.yml").write_bytes(
        examples.joinpath("config.example.yml").read_bytes()
    )
    (dest / ".gitignore").write_bytes(
        examples.joinpath("gitignore").read_bytes()
    )

    if with_docs:
        docs_src = examples.joinpath("docs")
        docs_dest = dest / "docs"
        if docs_src.is_dir():
            for file in docs_src.rglob("*"):
                if file.is_file():
                    dst_file = docs_dest / file.relative_to(docs_src)
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    dst_file.write_bytes(file.read_bytes())

    if with_scripts:
        scripts_src = examples.joinpath("scripts")
        scripts_dest = dest / "scripts"
        if scripts_src.is_dir():
            for file in scripts_src.rglob("*"):
                if file.is_file():
                    dst_file = scripts_dest / file.relative_to(scripts_src)
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    dst_file.write_bytes(file.read_bytes())

    if with_pyproject:
        py_src = examples.joinpath("pyproject.toml")
        if py_src.is_file():
            (dest / "pyproject.toml").write_bytes(py_src.read_bytes())

    # Documentation template
    readme_src = examples.joinpath("README.md")
    if readme_src.is_file():
        (dest / "README.md").write_bytes(readme_src.read_bytes())

    # Copy bundled example tests
    tests_src = examples.joinpath("tests")
    tests_dest = dest / "tests"
    if tests_src.is_dir():
        for file in tests_src.rglob("*"):
            if file.is_file():
                dst_file = tests_dest / file.relative_to(tests_src)
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                dst_file.write_bytes(file.read_bytes())

    # Copy strategy entry point
    (dest / "strategy.py").write_bytes(
        examples.joinpath("strategy.py").read_bytes()
    )

    try:
        template_file = TEMPLATES[template]
    except KeyError:
        raise ValueError(f"unknown template: {template}")

    # Copy example DAG under ``dags/example_strategy.py``
    dags_dir = dest / "dags"
    dags_dir.mkdir(exist_ok=True)
    (dags_dir / "example_strategy.py").write_bytes(
        examples.joinpath(template_file).read_bytes()
    )

    if with_sample_data:
        data_dir = dest / "data"
        data_dir.mkdir(exist_ok=True)
        sample = examples.joinpath("data/sample_ohlcv.csv")
        if sample.is_file():
            (data_dir / "sample_ohlcv.csv").write_bytes(sample.read_bytes())

        # Copy example notebook for strategy analysis
        nb_src = examples.joinpath("notebooks/strategy_analysis_example.ipynb")
        if nb_src.is_file():
            nb_dest_dir = dest / "notebooks"
            nb_dest_dir.mkdir(exist_ok=True)
            (nb_dest_dir / "strategy_analysis_example.ipynb").write_bytes(
                nb_src.read_bytes()
            )



__all__ = ["create_project", "TEMPLATES"]
