from __future__ import annotations

from pathlib import Path

import pytest

from qmtl.interfaces.cli import config as config_cli
from qmtl.interfaces.config_templates import CONFIG_TEMPLATE_FILES, resolve_template


@pytest.mark.parametrize("profile", sorted(CONFIG_TEMPLATE_FILES))
def test_generate_writes_expected_template(tmp_path: Path, profile: str) -> None:
    output = tmp_path / "generated.yml"

    config_cli.run([
        "generate",
        "--profile",
        profile,
        "--output",
        str(output),
    ])

    expected = resolve_template(profile).read_text()
    assert output.read_text() == expected


def test_generate_refuses_to_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "qmtl.yml"
    output.write_text("existing")

    with pytest.raises(SystemExit) as exc:
        config_cli.run([
            "generate",
            "--profile",
            "minimal",
            "--output",
            str(output),
        ])

    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "already exists" in captured.err
    assert output.read_text() == "existing"


def test_generate_force_overwrites(tmp_path: Path) -> None:
    output = tmp_path / "qmtl.yml"
    output.write_text("existing")

    config_cli.run([
        "generate",
        "--profile",
        "maximal",
        "--output",
        str(output),
        "--force",
    ])

    expected = resolve_template("maximal").read_text()
    assert output.read_text() == expected


def test_generate_defaults_to_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    config_cli.run(["generate", "--profile", "minimal"])

    expected = resolve_template("minimal").read_text()
    assert Path("qmtl.yml").read_text() == expected
