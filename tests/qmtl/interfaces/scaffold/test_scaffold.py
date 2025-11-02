from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pytest

from qmtl.interfaces.scaffold import create_project


def _list_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def _list_dirs(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir()
    }


def _assert_absent(paths: Iterable[str], candidates: set[str]) -> None:
    for rel in paths:
        assert rel not in candidates, f"{rel} unexpectedly provisioned"


def test_create_project_provisions_core_contract(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    create_project(dest)

    files = _list_files(dest)
    dirs = _list_dirs(dest)

    # Core files that define the scaffold contract
    for rel in {
        "qmtl.yml",
        "config.example.yml",
        ".gitignore",
        "README.md",
        "strategy.py",
        "dags/example_strategy.py",
        "tests/nodes/test_sequence_generator_node.py",
        "templates/local_stack.example.yml",
        "templates/backend_stack.example.yml",
    }:
        assert rel in files, f"Missing scaffold asset: {rel}"

    # Project must expose reusable node packages for generators, indicators, transforms
    for package in ["nodes", "nodes/generators", "nodes/indicators", "nodes/transforms"]:
        assert package in dirs, f"Missing scaffold directory: {package}"
        assert any(
            candidate.startswith(f"{package}/") and candidate.endswith(".py")
            for candidate in files
        ), f"{package} does not contain Python templates"

    # Optional assets should be opt-in and therefore absent by default
    _assert_absent(
        [
            "docs/README.md",
            "scripts/example.py",
            "data/sample_ohlcv.csv",
            "notebooks/strategy_analysis_example.ipynb",
            "pyproject.toml",
        ],
        files,
    )


@pytest.mark.parametrize(
    "kwargs, expected_artifacts",
    [
        (
            {"with_docs": True, "with_scripts": True, "with_pyproject": True},
            {
                "docs/README.md",
                "scripts/example.py",
                "pyproject.toml",
            },
        ),
        (
            {"with_sample_data": True},
            {
                "data/sample_ohlcv.csv",
                "notebooks/strategy_analysis_example.ipynb",
            },
        ),
    ],
)
def test_create_project_optionals(tmp_path: Path, kwargs: dict[str, bool], expected_artifacts: set[str]) -> None:
    dest = tmp_path / "proj_opts"
    create_project(dest, **kwargs)

    files = _list_files(dest)
    for rel in expected_artifacts:
        assert rel in files, f"Optional asset not provisioned: {rel}"


@pytest.mark.parametrize(
    "template, expected_snippet",
    [
        ("general", "qmtl.examples.strategies.general_strategy"),
        ("branching", "class BranchingStrategy"),
        ("single_indicator", "class SingleIndicatorStrategy"),
        ("multi_indicator", "class MultiIndicatorStrategy"),
        ("state_machine", "class StateMachineStrategy"),
    ],
)
def test_create_project_uses_selected_template(tmp_path: Path, template: str, expected_snippet: str) -> None:
    dest = tmp_path / template
    create_project(dest, template=template)

    dag_source = (dest / "dags" / "example_strategy.py").read_text()
    assert expected_snippet in dag_source


def test_create_project_unknown_template(tmp_path: Path) -> None:
    dest = tmp_path / "proj_invalid"

    with pytest.raises(ValueError):
        create_project(dest, template="does-not-exist")

    # Ensure the canonical DAG entry point was not created when validation failed
    assert not (dest / "dags" / "example_strategy.py").exists()
