from pathlib import Path

from qmtl.interfaces.cli import main as cli_main
from qmtl.interfaces.scaffold import create_project


def test_create_project_matches_public_scaffold_shape(tmp_path: Path):
    dest = tmp_path / "proj"
    create_project(dest)

    assert (dest / "qmtl.yml").is_file()
    assert (dest / ".env.example").is_file()
    assert (dest / "strategies" / "__init__.py").is_file()
    assert (dest / "strategies" / "my_strategy.py").is_file()


def test_init_cli_v2_public_scaffold(tmp_path: Path):
    dest = tmp_path / "cli_v2_proj"
    result = cli_main(["init", str(dest)])
    assert result == 0

    assert (dest / "strategies" / "__init__.py").is_file()
    assert (dest / "strategies" / "my_strategy.py").is_file()
    assert (dest / "qmtl.yml").is_file()
    assert (dest / ".env.example").is_file()
