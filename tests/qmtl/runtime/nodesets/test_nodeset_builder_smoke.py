from __future__ import annotations

import pytest

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.nodesets.base import NodeSetBuilder
from qmtl.runtime.nodesets.recipes import NodeSetRecipe
from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.nodesets.resources import clear_shared_portfolios
from qmtl.runtime.nodesets.steps import StepSpec
from qmtl.runtime.nodesets.stubs import StubSizingNode
from qmtl.runtime.pipeline.execution_nodes import (
    SizingNode as RealSizingNode,
    PortfolioNode as RealPortfolioNode,
)


def test_nodeset_attach_passes_through():
    # Minimal signal node emitting an order intent
    signal = Node(name="signal", interval=1, period=1)
    builder = NodeSetBuilder()
    ns = builder.attach(signal, world_id="w1")
    # Feed through the chain; each stub passes the payload as-is
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 2.0}
    nodes = list(ns)
    assert len(nodes) == 8
    # pretrade
    out = Runner.feed_queue_data(nodes[0], signal.node_id, 1, 0, order)
    assert out == order
    # sizing
    out = Runner.feed_queue_data(nodes[1], nodes[0].node_id, 1, 0, out)
    assert out == order
    # execution
    out = Runner.feed_queue_data(nodes[2], nodes[1].node_id, 1, 0, out)
    assert out == order
    # order publish
    out = Runner.feed_queue_data(nodes[3], nodes[2].node_id, 1, 0, out)
    assert out == order
    # fills
    out = Runner.feed_queue_data(nodes[4], nodes[3].node_id, 1, 0, out)
    assert out == order
    # portfolio
    out = Runner.feed_queue_data(nodes[5], nodes[4].node_id, 1, 0, out)
    assert out == order
    # risk
    out = Runner.feed_queue_data(nodes[6], nodes[5].node_id, 1, 0, out)
    assert out == order
    # timing
    out = Runner.feed_queue_data(nodes[7], nodes[6].node_id, 1, 0, out)
    assert out == order


def test_nodeset_builder_world_scope_shares_portfolio():
    clear_shared_portfolios()
    signal1 = Node(name="sig1", interval=1, period=1)
    signal2 = Node(name="sig2", interval=1, period=1)
    builder = NodeSetBuilder(options=NodeSetOptions(portfolio_scope="world"))
    ns1 = builder.attach(signal1, world_id="world", scope="world")
    ns2 = builder.attach(signal2, world_id="world", scope="world")

    sizing1 = list(ns1)[1]
    sizing2 = list(ns2)[1]
    portfolio1 = getattr(sizing1, "portfolio", None)
    portfolio2 = getattr(sizing2, "portfolio", None)

    assert portfolio1 is not None
    assert portfolio1 is portfolio2
    assert getattr(list(ns1)[5], "portfolio", None) is portfolio1
    assert getattr(sizing1, "weight_fn", None) is not None


def test_nodeset_builder_accepts_factories():
    signal = Node(name="sig", interval=1, period=1)
    builder = NodeSetBuilder()
    seen: dict[str, str] = {}

    def sizing_factory(upstream, ctx):
        seen["world_id"] = ctx.world_id
        return RealSizingNode(
            upstream,
            portfolio=ctx.resources.portfolio,
            weight_fn=ctx.resources.weight_fn,
        )

    def portfolio_factory(upstream, ctx):
        return RealPortfolioNode(upstream, portfolio=ctx.resources.portfolio)

    nodeset = builder.attach(
        signal,
        world_id="world-x",
        name="custom",
        modes=("simulate", "paper"),
        sizing=sizing_factory,
        portfolio=portfolio_factory,
    )

    nodes = list(nodeset)
    assert isinstance(nodes[1], RealSizingNode)
    assert isinstance(nodes[5], RealPortfolioNode)
    assert seen["world_id"] == "world-x"
    assert nodeset.name == "custom"
    assert nodeset.modes == ("simulate", "paper")


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

    nodes = list(nodeset)
    assert isinstance(nodes[1], RealSizingNode)
    assert getattr(nodes[1], "world_id", None) == "world-demo"
    assert isinstance(nodes[5], RealPortfolioNode)
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
    sizing_node = list(nodeset)[1]

    assert isinstance(sizing_node, RealSizingNode)
    assert getattr(sizing_node, "portfolio", None) is not None
    assert getattr(sizing_node, "weight_fn", None) is not None


def test_step_spec_default_resets_recipe_override():
    signal = Node(name="reset-sig", interval=1, period=1)
    recipe = NodeSetRecipe(
        name="reset", steps={"sizing": StepSpec.from_factory(RealSizingNode, inject_portfolio=True)}
    )

    sized_nodeset = recipe.compose(signal, "world-reset")
    assert isinstance(list(sized_nodeset)[1], RealSizingNode)

    reverted = recipe.compose(signal, "world-reset", steps={"sizing": StepSpec.default()})
    assert isinstance(list(reverted)[1], StubSizingNode)


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
