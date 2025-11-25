from __future__ import annotations

import pytest

from qmtl.runtime.nodesets.base import NodeSet, NodeSetBuilder
from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.nodesets.recipes import NodeSetRecipe
from qmtl.runtime.nodesets.resources import clear_shared_portfolios
from qmtl.runtime.nodesets.steps import StepSpec
from qmtl.runtime.pipeline.execution_nodes import (
    PortfolioNode as RealPortfolioNode,
    SizingNode as RealSizingNode,
)
from qmtl.runtime.sdk.node import Node


def _collect_contract(nodeset: NodeSet) -> dict[str, object]:
    nodes = nodeset.nodes
    return {
        "world_ids": {getattr(node, "world_id", None) for node in nodes},
        "sizing": next((node for node in nodes if isinstance(node, RealSizingNode) or getattr(node, "name", "").endswith("_sizing")), None),
        "portfolio": next((node for node in nodes if isinstance(node, (RealPortfolioNode,))), None),
    }


def test_nodeset_attach_exposes_contract_metadata():
    signal = Node(name="signal", interval=1, period=1)
    builder = NodeSetBuilder(options=NodeSetOptions(portfolio_scope="strategy"))

    nodeset = builder.attach(
        signal,
        world_id="world-1",
        name="orders",
        modes=("simulate", "paper"),
    )

    description = nodeset.describe()
    capabilities = nodeset.capabilities()
    contract = _collect_contract(nodeset)

    assert description["name"] == "orders"
    assert description["entry"].startswith(signal.name)
    assert description["node_count"] >= 1
    assert capabilities == {"modes": ["simulate", "paper"], "portfolio_scope": "strategy"}
    assert contract["world_ids"] == {"world-1"}

    sizing_node = contract["sizing"]
    assert sizing_node is not None
    assert getattr(sizing_node, "portfolio", None) is not None
    assert getattr(sizing_node, "weight_fn", None) is not None


def test_nodeset_builder_world_scope_shares_portfolio():
    clear_shared_portfolios()
    signal1 = Node(name="sig1", interval=1, period=1)
    signal2 = Node(name="sig2", interval=1, period=1)
    builder = NodeSetBuilder(options=NodeSetOptions(portfolio_scope="world"))

    ns1 = builder.attach(signal1, world_id="world", scope="world")
    ns2 = builder.attach(signal2, world_id="world", scope="world")

    contract1 = _collect_contract(ns1)
    contract2 = _collect_contract(ns2)

    portfolio1 = getattr(contract1["sizing"], "portfolio", None)
    portfolio2 = getattr(contract2["sizing"], "portfolio", None)

    assert portfolio1 is not None
    assert portfolio1 is portfolio2


def test_nodeset_builder_passes_context_to_factories():
    signal = Node(name="sig", interval=1, period=1)
    builder = NodeSetBuilder()
    seen: dict[str, object] = {}

    def sizing_factory(upstream: Node, ctx):
        seen["world_id"] = ctx.world_id
        seen["scope"] = ctx.scope
        seen["options"] = ctx.options
        return RealSizingNode(
            upstream,
            portfolio=ctx.resources.portfolio,
            weight_fn=ctx.resources.weight_fn,
        )

    def portfolio_factory(upstream: Node, ctx):
        seen["portfolio_world_id"] = ctx.world_id
        return RealPortfolioNode(upstream, portfolio=ctx.resources.portfolio)

    nodeset = builder.attach(
        signal,
        world_id="world-x",
        name="custom",
        modes=("simulate",),
        sizing=sizing_factory,
        portfolio=portfolio_factory,
    )

    contract = _collect_contract(nodeset)

    assert isinstance(contract["sizing"], RealSizingNode)
    assert isinstance(contract["portfolio"], RealPortfolioNode)
    assert seen["world_id"] == "world-x"
    assert seen["portfolio_world_id"] == "world-x"
    assert seen["scope"] == "strategy"
    assert nodeset.name == "custom"
    assert nodeset.modes == ("simulate",)
    assert seen["options"].portfolio_scope == "strategy"


def test_nodeset_recipe_compose_uses_step_specs():
    signal = Node(name="recipe-sig", interval=1, period=1)
    recipe = NodeSetRecipe(
        name="demo",
        steps={
            "sizing": StepSpec.from_factory(
                RealSizingNode,
                inject_portfolio=True,
                inject_weight_fn=True,
            ),
            "portfolio": StepSpec.from_factory(
                RealPortfolioNode,
                inject_portfolio=True,
            ),
        },
    )

    nodeset = recipe.compose(signal, "world-demo")
    contract = _collect_contract(nodeset)

    assert isinstance(contract["sizing"], RealSizingNode)
    assert getattr(contract["sizing"], "world_id", None) == "world-demo"
    assert isinstance(contract["portfolio"], RealPortfolioNode)
    assert nodeset.name == "demo"


def test_step_spec_factory_injects_resources():
    signal = Node(name="spec-sig", interval=1, period=1)
    builder = NodeSetBuilder()
    spec = StepSpec.from_factory(
        RealSizingNode,
        inject_portfolio=True,
        inject_weight_fn=True,
    )

    nodeset = builder.attach(signal, world_id="world-spec", sizing=spec)
    sizing_node = _collect_contract(nodeset)["sizing"]

    assert isinstance(sizing_node, RealSizingNode)
    assert getattr(sizing_node, "portfolio", None) is not None
    assert getattr(sizing_node, "weight_fn", None) is not None


def test_step_spec_default_resets_recipe_override():
    signal = Node(name="reset-sig", interval=1, period=1)
    recipe = NodeSetRecipe(
        name="reset", steps={"sizing": StepSpec.from_factory(RealSizingNode, inject_portfolio=True)}
    )

    sized_nodeset = recipe.compose(signal, "world-reset")
    assert isinstance(_collect_contract(sized_nodeset)["sizing"], RealSizingNode)

    reverted = recipe.compose(signal, "world-reset", steps={"sizing": StepSpec.default()})
    reverted_sizing = _collect_contract(reverted)["sizing"]
    assert isinstance(reverted_sizing, Node)


def test_step_spec_requires_node_instance():
    signal = Node(name="bad-spec", interval=1, period=1)
    builder = NodeSetBuilder()

    def _bad_factory(upstream: Node, **_kwargs):
        return None

    bad_spec = StepSpec.from_factory(_bad_factory)

    with pytest.raises(TypeError):
        builder.attach(signal, world_id="bad-world", sizing=bad_spec)


def test_nodeset_recipe_rejects_unknown_step_key():
    with pytest.raises(KeyError):
        NodeSetRecipe(
            name="bad",
            steps={"not-a-step": StepSpec.from_factory(RealSizingNode, inject_portfolio=True)},
        )
