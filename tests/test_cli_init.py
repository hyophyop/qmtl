import qmtl.cli


def test_cli_init(tmp_path):
    tmp_dir = tmp_path / "proj"
    qmtl.cli.main(["init", "--path", str(tmp_dir)])

    assert (tmp_dir / "qmtl.yml").is_file()
    assert (tmp_dir / "strategy.py").is_file()
    nodes_dir = tmp_dir / "nodes"
    for pkg in ["generators", "indicators", "transforms"]:
        pkg_path = nodes_dir / pkg
        assert pkg_path.is_dir()
        assert (pkg_path / "__init__.py").is_file()


def test_cli_init_with_template(tmp_path):
    tmp_dir = tmp_path / "proj"
    qmtl.cli.main(["init", "--path", str(tmp_dir), "--strategy", "branching"])
    contents = (tmp_dir / "dags" / "example_strategy.py").read_text()
    assert "BranchingStrategy" in contents


def test_cli_list_templates(capsys):
    qmtl.cli.main(["init", "--list-templates", "--path", "foo"])
    out = capsys.readouterr().out.strip().splitlines()
    assert "branching" in out
    assert "general" in out


def test_cli_help_contains_doc_links(capsys):
    try:
        qmtl.cli.main(["init", "--help"])
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "docs/templates.md" in out
    assert "docs/strategy_workflow.md" in out
