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
    path: Path, template: str = "general", with_sample_data: bool = False
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
    (dest / "qmtl.yml").write_bytes(
        examples.joinpath("qmtl.yml").read_bytes()
    )
    (dest / "config.example.yml").write_bytes(
        examples.joinpath("config.example.yml").read_bytes()
    )
    (dest / ".gitignore").write_bytes(
        examples.joinpath("gitignore").read_bytes()
    )

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
