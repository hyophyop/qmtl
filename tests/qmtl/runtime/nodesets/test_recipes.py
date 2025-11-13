from __future__ import annotations

from qmtl.runtime.nodesets.recipes import NodeSetRecipe
from qmtl.runtime.nodesets.steps import StepSpec
from qmtl.runtime.pipeline.execution_nodes import SizingNode as RealSizingNode


def test_merge_step_overrides_handles_default_spec():
    recipe = NodeSetRecipe(
        name="defaults",
        steps={"sizing": StepSpec.from_factory(RealSizingNode, inject_portfolio=True)},
    )

    resolved = recipe._merge_step_overrides({"sizing": StepSpec.default()})

    assert "sizing" not in resolved


def test_merge_step_overrides_accepts_explicit_override():
    recipe = NodeSetRecipe(name="explicit")
    sizing_override = StepSpec.from_factory(RealSizingNode, inject_portfolio=True)

    resolved = recipe._merge_step_overrides({"sizing": sizing_override})

    assert resolved["sizing"] is sizing_override


def test_apply_legacy_components_passthrough_function():
    recipe = NodeSetRecipe(name="legacy")

    def legacy_factory(upstream, ctx):  # pragma: no cover - signature inspected only
        return upstream

    resolved, passthrough = recipe._apply_legacy_components({}, {"sizing": legacy_factory})

    assert resolved == {}
    assert passthrough["sizing"] is legacy_factory


def test_build_attach_kwargs_prefers_resolved_steps():
    recipe = NodeSetRecipe(name="attach")
    step_spec = StepSpec.from_factory(RealSizingNode, inject_portfolio=True)
    legacy_factory = lambda upstream, ctx: upstream  # noqa: E731 - simple passthrough for test

    kwargs = recipe._build_attach_kwargs(
        {"sizing": step_spec}, {"sizing": legacy_factory}
    )

    assert kwargs["sizing"] is step_spec
