from qmtl.interfaces.cli import init as init_cli


def test_cli_init(tmp_path):
    tmp_dir = tmp_path / "proj"
    init_cli.run(["--path", str(tmp_dir)])

    assert (tmp_dir / "qmtl.yml").is_file()
    assert (tmp_dir / "strategy.py").is_file()
    nodes_dir = tmp_dir / "nodes"
    for pkg in ["generators", "indicators", "transforms"]:
        pkg_path = nodes_dir / pkg
        assert pkg_path.is_dir()
        assert (pkg_path / "__init__.py").is_file()


def test_cli_init_with_template(tmp_path):
    tmp_dir = tmp_path / "proj"
    init_cli.run(["--path", str(tmp_dir), "--strategy", "branching"])
    contents = (tmp_dir / "dags" / "example_strategy.py").read_text()
    assert "BranchingStrategy" in contents


def test_cli_list_presets_shim(monkeypatch):
    captured: dict[str, list[str] | None] = {}

    def fake_run(argv=None):
        captured["argv"] = argv

    monkeypatch.setattr("qmtl.interfaces.cli.presets.run", fake_run)

    init_cli.run(["--list-presets"])

    assert captured["argv"] == []


def test_cli_list_templates_shim(monkeypatch):
    captured: dict[str, list[str] | None] = {}

    def fake_run(argv=None):
        captured["argv"] = argv

    monkeypatch.setattr("qmtl.interfaces.cli.presets.run", fake_run)

    init_cli.run(["--list-templates"])

    assert captured["argv"] == ["--show-legacy-templates"]


def test_cli_help_contains_doc_links(capsys):
    try:
        init_cli.run(["--help"])
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "docs/reference/templates.md" in out
    assert "docs/guides/strategy_workflow.md" in out
