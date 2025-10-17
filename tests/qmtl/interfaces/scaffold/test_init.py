from pathlib import Path
import subprocess
import sys

from qmtl.interfaces.scaffold import create_project


def _assert_backend_templates(dest: Path) -> None:
    templates_dir = dest / "templates"
    assert (templates_dir / "local_stack.example.yml").is_file()
    assert (templates_dir / "backend_stack.example.yml").is_file()


def test_create_project(tmp_path: Path):
    dest = tmp_path / "proj"
    create_project(dest)
    assert (dest / "qmtl.yml").is_file()
    assert (dest / "strategy.py").is_file()
    assert (dest / "dags" / "example_strategy.py").is_file()
    assert (dest / ".gitignore").is_file()
    assert (dest / "README.md").is_file()
    assert (dest / "tests" / "nodes" / "test_sequence_generator_node.py").is_file()
    dag = dest / "dags" / "example_strategy"
    assert (dag / "__init__.py").is_file()
    assert (dag / "config.yaml").is_file()
    _assert_backend_templates(dest)


def test_create_project_with_sample_data(tmp_path: Path):
    dest = tmp_path / "proj_data"
    create_project(dest, with_sample_data=True)
    assert (dest / "config.example.yml").is_file()
    assert (dest / "data" / "sample_ohlcv.csv").is_file()
    assert (dest / "dags" / "example_strategy.py").is_file()
    assert (dest / ".gitignore").is_file()
    assert (dest / "README.md").is_file()
    assert (dest / "tests" / "nodes" / "test_sequence_generator_node.py").is_file()
    _assert_backend_templates(dest)


def test_create_project_with_optionals(tmp_path: Path):
    dest = tmp_path / "proj_opts"
    create_project(dest, with_docs=True, with_scripts=True, with_pyproject=True)
    assert (dest / "docs" / "README.md").is_file()
    assert (dest / "scripts" / "example.py").is_file()
    assert (dest / "pyproject.toml").is_file()
    _assert_backend_templates(dest)


def test_init_cli(tmp_path: Path):
    dest = tmp_path / "cli_proj"
    result = subprocess.run([
        sys.executable,
        "-m",
        "qmtl",
        "project",
        "init",
        "--path",
        str(dest),
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert (dest / "qmtl.yml").is_file()
    assert (dest / "strategy.py").is_file()
    assert (dest / "dags" / "example_strategy.py").is_file()
    assert (dest / ".gitignore").is_file()
    assert (dest / "README.md").is_file()
    assert (dest / "tests" / "nodes" / "test_sequence_generator_node.py").is_file()
    dag = dest / "dags" / "example_strategy"
    assert (dag / "__init__.py").is_file()
    assert (dag / "config.yaml").is_file()
    _assert_backend_templates(dest)


def test_init_cli_with_optionals(tmp_path: Path):
    dest = tmp_path / "cli_proj_opts"
    result = subprocess.run([
        sys.executable,
        "-m",
        "qmtl",
        "project",
        "init",
        "--path",
        str(dest),
        "--with-docs",
        "--with-scripts",
        "--with-pyproject",
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert (dest / "docs" / "README.md").is_file()
    assert (dest / "scripts" / "example.py").is_file()
    assert (dest / "pyproject.toml").is_file()
    _assert_backend_templates(dest)


def test_init_cli_with_sample_data(tmp_path: Path):
    dest = tmp_path / "cli_proj_data"
    result = subprocess.run([
        sys.executable,
        "-m",
        "qmtl",
        "project",
        "init",
        "--path",
        str(dest),
        "--with-sample-data",
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert (dest / "config.example.yml").is_file()
    assert (dest / "data" / "sample_ohlcv.csv").is_file()
    assert (dest / "dags" / "example_strategy.py").is_file()
    assert (dest / ".gitignore").is_file()
    assert (dest / "README.md").is_file()
    assert (dest / "tests" / "nodes" / "test_sequence_generator_node.py").is_file()
    _assert_backend_templates(dest)
