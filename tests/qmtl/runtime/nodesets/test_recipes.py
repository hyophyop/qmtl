from __future__ import annotations

from typing import ClassVar

from qmtl.runtime.nodesets.base import NodeSet, NodeSetBuilder, NodeSetOptions
from qmtl.runtime.nodesets.recipes import (
    NodeSetRecipe,
    StepResolutionContext,
)
from qmtl.runtime.nodesets.steps import STEP_ORDER, StepSpec
from qmtl.runtime.pipeline.execution_nodes import SizingNode as RealSizingNode
from qmtl.runtime.sdk import Node


def _make_resolution_context(
    defaults: dict[str, StepSpec] | None = None,
    overrides: dict | None = None,
    legacy: dict | None = None,
) -> StepResolutionContext:
    return StepResolutionContext(
        defaults or {},
        overrides=overrides or {},
        legacy_components=legacy or {},
        normalizer=lambda steps, drop_defaults: NodeSetRecipe._normalize_steps(
            steps, drop_defaults=drop_defaults
        ),
    )


def test_step_resolution_context_drops_default_override() -> None:
    context = _make_resolution_context(
        defaults={
            "sizing": StepSpec.from_factory(RealSizingNode, inject_portfolio=True)
        },
        overrides={"sizing": StepSpec.default()},
    )

    attach_kwargs = context.attach_kwargs()

    assert "sizing" not in attach_kwargs


def test_step_resolution_context_accepts_explicit_override() -> None:
    sizing_override = StepSpec.from_factory(RealSizingNode, inject_portfolio=True)

    context = _make_resolution_context(overrides={"sizing": sizing_override})

    attach_kwargs = context.attach_kwargs()

    assert attach_kwargs["sizing"] is sizing_override


def test_step_resolution_context_records_legacy_passthrough() -> None:
    def legacy_factory(upstream, ctx):  # pragma: no cover - signature inspected only
        return upstream

    context = _make_resolution_context(legacy={"sizing": legacy_factory})

    attach_kwargs = context.attach_kwargs()

    assert attach_kwargs["sizing"] is legacy_factory


def test_step_resolution_context_attach_prefers_resolved_steps() -> None:
    step_spec = StepSpec.from_factory(RealSizingNode, inject_portfolio=True)

    def legacy_factory(upstream, ctx):  # pragma: no cover - signature inspected only
        return upstream

    context = _make_resolution_context(
        overrides={"sizing": step_spec}, legacy={"sizing": legacy_factory}
    )

    attach_kwargs = context.attach_kwargs()

    assert attach_kwargs["sizing"] is step_spec


def test_compose_preserves_legacy_execution_pipeline() -> None:
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
    recipe = NodeSetRecipe(name="legacy-path", builder=builder)

    signal = Node(compute_fn=lambda view: None, name="signal")

    def legacy_execution(upstream, ctx):  # pragma: no cover - signature inspected only
        return upstream

    def legacy_publish(upstream, ctx):  # pragma: no cover - signature inspected only
        return upstream

    recipe.compose(
        signal,
        "world-1",
        execution=legacy_execution,
        order_publish=legacy_publish,
    )

    captured_builder = CaptureBuilder.last_instance
    assert captured_builder is not None
    assert captured_builder.attached_kwargs is not None
    assert captured_builder.attached_kwargs["execution"] is legacy_execution
    assert captured_builder.attached_kwargs["order_publish"] is legacy_publish

