from pathlib import Path

import pytest

from qmtl.interfaces.cli import main as cli_main
from qmtl.interfaces.layers import Layer, LayerComposer, PresetConfig, ValidationResult
from qmtl.interfaces.scaffold import create_project
from tests.qmtl.interfaces._cli_tokens import resolve_cli_tokens


def _assert_backend_templates(dest: Path) -> None:
    templates_dir = dest / "templates"
    assert (templates_dir / "local_stack.example.yml").is_file()
    assert (templates_dir / "backend_stack.example.yml").is_file()


PROJECT_INIT_TOKENS = resolve_cli_tokens("qmtl.interfaces.cli.project", "qmtl.interfaces.cli.init")
PROJECT_ADD_LAYER_TOKENS = resolve_cli_tokens("qmtl.interfaces.cli.project", "qmtl.interfaces.cli.add_layer")
PROJECT_LIST_LAYERS_TOKENS = resolve_cli_tokens("qmtl.interfaces.cli.project", "qmtl.interfaces.cli.list_layers")
PROJECT_VALIDATE_TOKENS = resolve_cli_tokens("qmtl.interfaces.cli.project", "qmtl.interfaces.cli.validate")


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
        (
            [],
            {
                "with_sample_data": False,
                "with_docs": False,
                "with_scripts": False,
                "with_pyproject": False,
                "config_profile": "minimal",
            },
        ),
        (
            ["--with-docs", "--with-scripts", "--with-pyproject"],
            {
                "with_sample_data": False,
                "with_docs": True,
                "with_scripts": True,
                "with_pyproject": True,
                "config_profile": "minimal",
            },
        ),
        (
            ["--with-sample-data"],
            {
                "with_sample_data": True,
                "with_docs": False,
                "with_scripts": False,
                "with_pyproject": False,
                "config_profile": "minimal",
            },
        ),
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
        config_profile: str = "minimal",
    ) -> None:
        calls["path"] = path
        calls["kwargs"] = {
            "template": template,
            "with_sample_data": with_sample_data,
            "with_docs": with_docs,
            "with_scripts": with_scripts,
            "with_pyproject": with_pyproject,
            "config_profile": config_profile,
        }

    monkeypatch.setattr("qmtl.interfaces.cli.init.create_project", fake_create_project)

    cli_main([*PROJECT_INIT_TOKENS, "--path", str(dest), "--strategy", "general", *extra_args])

    assert calls["path"] == dest
    assert calls["kwargs"] == {"template": "general", **expected_flags}


def test_init_cli_with_preset(monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture):
    dest = tmp_path / "preset_proj"
    preset = PresetConfig(
        name="minimal",
        description="Minimal preset",
        layers=[Layer.DATA, Layer.SIGNAL],
    )
    calls: dict[str, object] = {}

    class DummyPresetLoader:
        def list_presets(self):
            return ["minimal"]

        def get_preset(self, name: str):
            calls["preset"] = name
            return preset if name == "minimal" else None

    class DummyComposer:
        def compose(
            self,
            *,
            layers,
            dest,
            template_choices=None,
            force=False,
            config_profile: str = "minimal",
        ):
            calls["compose"] = {
                "layers": layers,
                "dest": dest,
                "template_choices": template_choices,
                "force": force,
                "config_profile": config_profile,
            }
            return ValidationResult(valid=True)

    monkeypatch.setattr("qmtl.interfaces.cli.init.PresetLoader", lambda: DummyPresetLoader())
    monkeypatch.setattr("qmtl.interfaces.cli.init.LayerComposer", lambda: DummyComposer())

    cli_main([*PROJECT_INIT_TOKENS, "--path", str(dest), "--preset", "minimal"])
    out = capsys.readouterr().out

    assert calls["preset"] == "minimal"
    assert calls["compose"]["dest"] == dest
    assert calls["compose"]["layers"] == [Layer.DATA, Layer.SIGNAL]
    assert calls["compose"]["config_profile"] == "minimal"
    assert "Project created at" in out


def test_init_cli_with_layers(monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture):
    dest = tmp_path / "layers_proj"
    calls: dict[str, object] = {}

    class DummyValidator:
        def __init__(self):
            self.seen = {}

        def get_minimal_layer_set(self, target_layers):
            self.seen["target"] = target_layers
            return [Layer.DATA, Layer.SIGNAL, Layer.EXECUTION]

        def validate_layers(self, layers):
            calls["validated_layers"] = list(layers)
            return ValidationResult(valid=True)

        def validate_add_layer(self, existing_layers, new_layer):
            raise AssertionError("validate_add_layer should not be called in init")

    class DummyComposer:
        def __init__(self):
            self.validator = DummyValidator()

        def compose(
            self,
            *,
            layers,
            dest,
            template_choices=None,
            force=False,
            config_profile: str = "minimal",
        ):
            calls["compose"] = {
                "layers": layers,
                "dest": dest,
                "template_choices": template_choices,
                "force": force,
                "config_profile": config_profile,
            }
            return ValidationResult(valid=True)

    dummy_validator = DummyValidator()

    monkeypatch.setattr("qmtl.interfaces.cli.init.LayerValidator", lambda: dummy_validator)
    monkeypatch.setattr("qmtl.interfaces.cli.init.LayerComposer", lambda: DummyComposer())

    cli_main([*PROJECT_INIT_TOKENS, "--path", str(dest), "--layers", "execution"])
    out = capsys.readouterr().out

    assert dummy_validator.seen["target"] == [Layer.EXECUTION]
    assert calls["compose"]["layers"] == [Layer.DATA, Layer.SIGNAL, Layer.EXECUTION]
    assert calls["compose"]["config_profile"] == "minimal"
    assert "Project created at" in out


def test_init_cli_list_presets(monkeypatch, capsys: pytest.CaptureFixture):
    class DummyPresetLoader:
        def list_presets(self):
            return ["minimal", "production"]

        def get_preset(self, name: str):
            return PresetConfig(
                name=name,
                description=f"{name} preset",
                layers=[Layer.DATA, Layer.SIGNAL],
            )

    monkeypatch.setattr("qmtl.interfaces.cli.init.PresetLoader", lambda: DummyPresetLoader())

    cli_main([*PROJECT_INIT_TOKENS, "--list-presets"])
    out = capsys.readouterr().out

    assert "Available presets:" in out
    assert "minimal" in out
    assert "production" in out


def test_init_cli_list_layers(capsys: pytest.CaptureFixture):
    cli_main([*PROJECT_INIT_TOKENS, "--list-layers"])
    out = capsys.readouterr().out

    assert "Available layers:" in out
    assert "data" in out
    assert "signal" in out


def test_add_layer_cli(monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture):
    dest = tmp_path / "existing_proj"
    dest.mkdir()
    calls: dict[str, object] = {}

    class DummyComposer:
        def add_layer(self, *, dest, layer, template_name=None, force=False):
            calls["add_layer"] = {
                "dest": dest,
                "layer": layer,
                "template_name": template_name,
                "force": force,
            }
            return ValidationResult(valid=True)

    monkeypatch.setattr("qmtl.interfaces.cli.add_layer.LayerComposer", lambda: DummyComposer())

    cli_main([*PROJECT_ADD_LAYER_TOKENS, "--path", str(dest), "monitoring"])
    out = capsys.readouterr().out

    assert calls["add_layer"]["dest"] == dest
    assert calls["add_layer"]["layer"] == Layer.MONITORING
    assert "Layer 'monitoring' added to project" in out


def test_list_layers_cli(capsys: pytest.CaptureFixture):
    cli_main([*PROJECT_LIST_LAYERS_TOKENS])
    out = capsys.readouterr().out

    assert "Available layers:" in out
    assert "data" in out
    assert "signal" in out


def test_list_layers_cli_with_templates(capsys: pytest.CaptureFixture):
    cli_main([*PROJECT_LIST_LAYERS_TOKENS, "--show-templates", "--show-requires"])
    out = capsys.readouterr().out

    # Expect at least one template line to be printed
    assert "stream_input" in out or "single_indicator" in out


def test_validate_cli_success(tmp_path: Path, capsys: pytest.CaptureFixture):
    dest = tmp_path / "valid_project"
    composer = LayerComposer()
    composer.compose(
        layers=[Layer.DATA, Layer.SIGNAL],
        dest=dest,
    )

    cli_main([*PROJECT_VALIDATE_TOKENS, "--path", str(dest)])
    out = capsys.readouterr().out

    assert "is valid" in out


def test_validate_cli_failure(tmp_path: Path, capsys: pytest.CaptureFixture):
    dest = tmp_path / "invalid_project"
    dest.mkdir()

    with pytest.raises(SystemExit):
        cli_main([*PROJECT_VALIDATE_TOKENS, "--path", str(dest)])

    out = capsys.readouterr().out
    assert "Validation failed" in out or "does not exist" in out
