from __future__ import annotations

from collections.abc import Iterable

from ..exceptions import NodeValidationError
from .base import Node

__all__ = ["ProcessingNode"]


class ProcessingNode(Node):
    """Node that processes data from one or more upstream nodes."""

    def __init__(self, input: Node | Iterable[Node], *args, **kwargs) -> None:
        super().__init__(input=input, *args, **kwargs)
        if not self.inputs:
            raise NodeValidationError(
                "processing node requires at least one upstream (node.input에 올바른 업스트림 노드를 지정했는지 확인하세요)"
            )

