from pathlib import Path

from qmtl.scaffold import (
    copy_base_files,
    copy_dags,
    copy_docs,
    copy_nodes,
    copy_pyproject,
    copy_sample_data,
    copy_scripts,
)


def test_copy_nodes(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    copy_nodes(dest)
    assert (dest / "nodes" / "generators" / "sequence.py").is_file()
    assert (dest / "nodes" / "indicators" / "average.py").is_file()
    assert (dest / "nodes" / "transforms" / "scale.py").is_file()


def test_copy_dags(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    copy_dags(dest, "general")
    assert (dest / "dags" / "example_strategy.py").is_file()
    assert (dest / "dags" / "example_strategy" / "config.yaml").is_file()


def test_copy_docs(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    copy_docs(dest)
    assert (dest / "docs" / "README.md").is_file()


def test_copy_scripts(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    copy_scripts(dest)
    assert (dest / "scripts" / "example.py").is_file()


def test_copy_sample_data(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    copy_sample_data(dest)
    assert (dest / "data" / "sample_ohlcv.csv").is_file()
    assert (dest / "notebooks" / "strategy_analysis_example.ipynb").is_file()


def test_copy_pyproject(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    copy_pyproject(dest)
    assert (dest / "pyproject.toml").is_file()


def test_copy_base_files(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    copy_base_files(dest)
    assert (dest / "qmtl.yml").is_file()
    assert (dest / "config.example.yml").is_file()
    assert (dest / ".gitignore").is_file()
    assert (dest / "README.md").is_file()
    assert (dest / "strategy.py").is_file()
    assert (
        dest / "tests" / "nodes" / "test_sequence_generator_node.py"
    ).is_file()

