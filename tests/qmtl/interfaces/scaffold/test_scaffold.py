from __future__ import annotations

from pathlib import Path

import pytest

from qmtl.interfaces.scaffold import create_project, create_public_project


def test_create_public_project_provisions_blessed_scaffold(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    create_public_project(dest)

    assert (dest / "qmtl.yml").is_file()
    assert (dest / ".env.example").is_file()
    assert (dest / "strategies" / "__init__.py").is_file()
    assert (dest / "strategies" / "my_strategy.py").is_file()

    assert not (dest / "strategy.py").exists()
    assert not (dest / "dags").exists()
    assert not (dest / "nodes").exists()
    assert not (dest / "templates").exists()


def test_create_project_compat_wrapper_reuses_blessed_scaffold(tmp_path: Path) -> None:
    dest = tmp_path / "compat"
    create_project(dest, with_sample_data=True, with_docs=True, with_scripts=True, with_pyproject=True)

    assert (dest / "qmtl.yml").is_file()
    assert (dest / ".env.example").is_file()
    assert (dest / "strategies" / "__init__.py").is_file()
    assert (dest / "strategies" / "my_strategy.py").is_file()

    assert (dest / "data" / "sample_ohlcv.csv").is_file()
    assert (dest / "notebooks" / "strategy_analysis_example.ipynb").is_file()
    assert (dest / "docs" / "README.md").is_file()
    assert (dest / "scripts" / "example.py").is_file()
    assert (dest / "pyproject.toml").is_file()


def test_create_project_rejects_legacy_template_variants(tmp_path: Path) -> None:
    dest = tmp_path / "legacy"

    with pytest.raises(ValueError, match="Legacy scaffold template selection"):
        create_project(dest, template="branching")
