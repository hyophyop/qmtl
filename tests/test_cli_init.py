import qmtl.cli


def test_cli_init(tmp_path):
    tmp_dir = tmp_path / "proj"
    qmtl.cli.main(["init", "--path", str(tmp_dir)])

    assert (tmp_dir / "qmtl.yml").is_file()
    assert (tmp_dir / "strategy.py").is_file()
    for pkg in ["generators", "indicators", "transforms"]:
        pkg_path = tmp_dir / pkg
        assert pkg_path.is_dir()
        assert (pkg_path / "__init__.py").is_file()
