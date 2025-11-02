import pytest

from qmtl.runtime.sdk import Node, StreamInput
from qmtl.runtime.nodesets import registry as registry_module
from qmtl.runtime.nodesets.registry import make, list_registered


def test_nodeset_registry_has_ccxt_spot():
    assert "ccxt_spot" in list_registered()


def test_nodeset_registry_make_ccxt_spot_simulate():
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda v: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})
    ns = make("ccxt_spot", signal, "world", exchange_id="binance")
    nodes = list(ns)
    assert ns.head is nodes[0] and ns.tail is nodes[-1]
    assert len(nodes) == 8


def test_nodeset_registry_has_ccxt_futures():
    assert "ccxt_futures" in list_registered()


def test_nodeset_registry_make_ccxt_futures_simulate():
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda v: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})
    ns = make("ccxt_futures", signal, "world")
    nodes = list(ns)
    assert ns.head is nodes[0] and ns.tail is nodes[-1]
    assert len(nodes) == 8


def test_nodeset_recipe_decorator_registers(monkeypatch):
    monkeypatch.setattr(registry_module, "_REGISTRY", {}, raising=False)
    monkeypatch.setattr(registry_module, "_DISCOVERED", True, raising=False)

    assert list_registered() == []

    @registry_module.nodeset_recipe("test_recipe")
    def _builder(*_args, **_kwargs):
        return "sentinel"

    assert list_registered() == ["test_recipe"]
    assert make("test_recipe") == "sentinel"


def test_nodeset_recipe_duplicate_name(monkeypatch):
    monkeypatch.setattr(registry_module, "_REGISTRY", {}, raising=False)
    monkeypatch.setattr(registry_module, "_DISCOVERED", True, raising=False)

    @registry_module.nodeset_recipe("test_recipe")
    def _builder(*_args, **_kwargs):
        return "sentinel"

    with pytest.raises(ValueError):

        @registry_module.nodeset_recipe("test_recipe")
        def _other_builder():
            return "other"

    # Re-registering the same callable should be a no-op.
    registry_module.register("test_recipe", _builder)
    assert list_registered() == ["test_recipe"]
