from pathlib import Path

import pytest

from qmtl.interfaces.cli import main as cli_main
from qmtl.interfaces.scaffold import create_project
from tests.qmtl.interfaces._cli_tokens import resolve_cli_tokens


def _assert_backend_templates(dest: Path) -> None:
    templates_dir = dest / "templates"
    assert (templates_dir / "local_stack.example.yml").is_file()
    assert (templates_dir / "backend_stack.example.yml").is_file()


PROJECT_INIT_TOKENS = resolve_cli_tokens("qmtl.interfaces.cli.project", "qmtl.interfaces.cli.init")


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


@pytest.mark.parametrize(
    ("extra_args", "expected_flags"),
    [
        ([], {"with_sample_data": False, "with_docs": False, "with_scripts": False, "with_pyproject": False}),
        (
            ["--with-docs", "--with-scripts", "--with-pyproject"],
            {"with_sample_data": False, "with_docs": True, "with_scripts": True, "with_pyproject": True},
        ),
        (["--with-sample-data"], {"with_sample_data": True, "with_docs": False, "with_scripts": False, "with_pyproject": False}),
    ],
)
def test_init_cli_dispatch(monkeypatch, tmp_path: Path, extra_args, expected_flags):
    dest = tmp_path / "cli_proj"
    calls: dict[str, object] = {}

    def fake_create_project(
        path: Path,
        *,
        template: str = "general",
        with_sample_data: bool = False,
        with_docs: bool = False,
        with_scripts: bool = False,
        with_pyproject: bool = False,
    ) -> None:
        calls["path"] = path
        calls["kwargs"] = {
            "template": template,
            "with_sample_data": with_sample_data,
            "with_docs": with_docs,
            "with_scripts": with_scripts,
            "with_pyproject": with_pyproject,
        }

    monkeypatch.setattr("qmtl.interfaces.cli.init.create_project", fake_create_project)

    cli_main([*PROJECT_INIT_TOKENS, "--path", str(dest), *extra_args])

    assert calls["path"] == dest
    assert calls["kwargs"] == {"template": "general", **expected_flags}
