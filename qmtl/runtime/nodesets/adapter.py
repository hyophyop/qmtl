from __future__ import annotations

"""Adapters and port descriptors for Node Sets.

A Node Set adapter declares the black-box input/output ports of a Node Set and
knows how to wire external upstream nodes to the internal chain. This enables
Node Sets to be used like Nodes (accepting multiple upstreams) while preserving
encapsulation of internals.
"""

from dataclasses import dataclass
from typing import Callable, Iterable

from qmtl.runtime.sdk.node import Node

from .base import NodeSet
from .options import NodeSetOptions


@dataclass(frozen=True)
class PortSpec:
    name: str
    required: bool = True
    description: str | None = None


@dataclass(frozen=True)
class NodeSetDescriptor:
    name: str
    inputs: tuple[PortSpec, ...]
    outputs: tuple[PortSpec, ...]


class NodeSetAdapter:
    """Base adapter for building a Node Set from external inputs.

    Subclasses must define a :pyattr:`descriptor` and implement
    :py:meth:`build` to compose and return a :class:`NodeSet`.
    """

    descriptor: NodeSetDescriptor

    def validate_inputs(self, inputs: dict[str, Node]) -> None:
        missing = [p.name for p in self.descriptor.inputs if p.required and p.name not in inputs]
        if missing:
            raise ValueError(f"missing required Node Set inputs: {', '.join(missing)}")

    def build(
        self,
        inputs: dict[str, Node],
        *,
        world_id: str,
        options: NodeSetOptions | None = None,
    ) -> NodeSet:  # pragma: no cover - interface
        raise NotImplementedError


__all__ = ["PortSpec", "NodeSetDescriptor", "NodeSetAdapter"]

