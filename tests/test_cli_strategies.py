import sys
import types
from qmtl.cli import main


def test_strategies_subcommand_invokes_strategy(monkeypatch):
    fake_pkg = types.ModuleType("strategies")
    fake_mod = types.ModuleType("strategies.strategy")
    called: list[bool] = []

    def fake_main() -> None:
        called.append(True)

    fake_mod.main = fake_main
    fake_pkg.strategy = fake_mod
    monkeypatch.setitem(sys.modules, "strategies", fake_pkg)
    monkeypatch.setitem(sys.modules, "strategies.strategy", fake_mod)

    main(["strategies"])
    assert called
