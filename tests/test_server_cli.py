import pytest
from qmtl.dagmanager.server import main


def test_server_help(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "qmtl-dagmgr-server" in capsys.readouterr().out
