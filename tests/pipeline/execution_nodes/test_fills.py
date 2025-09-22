from __future__ import annotations

from qmtl.pipeline.execution_nodes.fills import FillIngestNode


def test_fill_ingest_defaults() -> None:
    node = FillIngestNode()
    assert node.name == "fill_ingest"
    assert node.period == 1
