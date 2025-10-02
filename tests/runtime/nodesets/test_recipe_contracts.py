import pytest

from qmtl.runtime.nodesets.recipes import CCXT_SPOT_DESCRIPTOR
from qmtl.runtime.nodesets.registry import make
from qmtl.runtime.nodesets.resources import clear_shared_portfolios
from qmtl.runtime.pipeline.execution_nodes import (
    SizingNode as RealSizingNode,
    PortfolioNode as RealPortfolioNode,
)
from qmtl.runtime.sdk import StreamInput


RECIPE_MATRIX = {
    "ccxt_spot": {
        "params": {"exchange_id": "binance"},
        "descriptor": CCXT_SPOT_DESCRIPTOR,
    },
    "ccxt_futures": {
        "params": {"exchange_id": "binanceusdm"},
        "descriptor": None,
    },
}


@pytest.fixture(autouse=True)
def _reset_shared_portfolios():
    clear_shared_portfolios()
    yield
    clear_shared_portfolios()


@pytest.mark.parametrize(
    "recipe_name, config",
    [(name, data) for name, data in RECIPE_MATRIX.items()],
)
def test_registered_recipe_contracts(recipe_name, config):
    world_id = "test-world"
    signal = StreamInput(tags=["alpha_signal"], interval="1m", period=1)

    nodeset = make(recipe_name, signal, world_id, **config["params"])

    assert len(nodeset.nodes) == 8
    assert nodeset.capabilities()["modes"] == ["simulate", "paper", "live"]
    assert nodeset.portfolio_scope == "strategy"
    for node in nodeset:
        mark = getattr(node, "world_id", None)
        if mark is not None:
            assert mark == world_id

    sizing = nodeset.nodes[1]
    portfolio = nodeset.nodes[5]
    assert isinstance(sizing, RealSizingNode)
    assert isinstance(portfolio, RealPortfolioNode)
    assert sizing.portfolio is portfolio.portfolio
    assert callable(sizing.weight_fn)

    descriptor = config["descriptor"]
    if descriptor is None:
        assert nodeset.descriptor is None
        assert nodeset.describe()["ports"] is None
    else:
        assert nodeset.descriptor is descriptor
        description = nodeset.describe()
        assert description["ports"] is not None
        assert description["ports"]["inputs"][0]["name"] == "signal"
        assert description["ports"]["outputs"][0]["name"] == "orders"
