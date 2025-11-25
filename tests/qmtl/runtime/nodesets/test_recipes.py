from __future__ import annotations

from typing import ClassVar
import pytest

from qmtl.runtime.nodesets.base import NodeSet, NodeSetBuilder, NodeSetOptions
from qmtl.runtime.nodesets.recipes import NodeSetRecipe
from qmtl.runtime.nodesets.steps import STEP_ORDER, StepSpec
from qmtl.runtime.pipeline.execution_nodes import SizingNode as RealSizingNode
from qmtl.runtime.sdk import Node


def _capture_recipe(builder: NodeSetBuilder | None = None) -> tuple[NodeSetRecipe, Node]:
    recipe = NodeSetRecipe(
        name="capture",
        builder=builder or NodeSetBuilder(),
        steps={
            "sizing": StepSpec.from_factory(RealSizingNode, inject_portfolio=True),
        },
    )
    signal = Node(compute_fn=lambda view: None, name="signal")
    return recipe, signal


def test_compose_drops_default_override() -> None:
    class CaptureBuilder(NodeSetBuilder):
        last_instance: ClassVar[CaptureBuilder | None] = None

        def __init__(self, *, options: NodeSetOptions | None = None) -> None:
            super().__init__(options=options)
            type(self).last_instance = self
            self.attached_kwargs: dict | None = None

        def attach(self, signal: Node, **kwargs):
            attach_kwargs = {key: kwargs[key] for key in kwargs if key in STEP_ORDER}
            self.attached_kwargs = attach_kwargs
            return NodeSet((signal,), name="capture")

    builder = CaptureBuilder()
    recipe, signal = _capture_recipe(builder)

    recipe.compose(
        signal,
        "world-1",
        steps={"sizing": StepSpec.default()},
    )

    captured_builder = CaptureBuilder.last_instance
    assert captured_builder is not None
    assert captured_builder.attached_kwargs is not None
    assert "sizing" not in captured_builder.attached_kwargs


def test_compose_accepts_explicit_override() -> None:
    class CaptureBuilder(NodeSetBuilder):
        last_instance: ClassVar[CaptureBuilder | None] = None

        def __init__(self, *, options: NodeSetOptions | None = None) -> None:
            super().__init__(options=options)
            type(self).last_instance = self
            self.attached_kwargs: dict | None = None

        def attach(self, signal: Node, **kwargs):
            attach_kwargs = {key: kwargs[key] for key in kwargs if key in STEP_ORDER}
            self.attached_kwargs = attach_kwargs
            return NodeSet((signal,), name="capture")

    builder = CaptureBuilder()
    recipe, signal = _capture_recipe(builder)
    sizing_override = StepSpec.from_factory(RealSizingNode, inject_portfolio=False)

    recipe.compose(
        signal,
        "world-1",
        steps={"sizing": sizing_override},
    )

    captured_builder = CaptureBuilder.last_instance
    assert captured_builder is not None
    assert captured_builder.attached_kwargs is not None
    assert captured_builder.attached_kwargs["sizing"] is sizing_override


def test_compose_raises_for_unknown_step() -> None:
    recipe, signal = _capture_recipe()

    with pytest.raises(KeyError):
        recipe.compose(signal, "world-1", steps={"unknown": StepSpec.default()})
