import pandas as pd
import pytest

from qmtl.sdk import SourceNode, Runner, Strategy, NodeValidationError


class _SchemaStrategy(Strategy):
    def setup(self):
        self.src = SourceNode(interval="1s", period=1, expected_schema={"a": "int64"})
        self.add_nodes([self.src])


def test_schema_violation_fail_mode():
    node = SourceNode(interval="1s", period=1, expected_schema={"a": "int64"})
    df = pd.DataFrame({"b": [1]})
    with pytest.raises(NodeValidationError) as exc:
        node.feed("u", 1, 1, df)
    assert "missing columns" in str(exc.value)
    assert node.node_id in str(exc.value)


@pytest.mark.asyncio
async def test_schema_violation_warn_mode(caplog):
    strategy = await Runner.offline_async(_SchemaStrategy, schema_enforcement="warn")
    node = strategy.src
    df = pd.DataFrame({"b": [1]})
    with caplog.at_level("WARNING"):
        node.feed("u", 1, 1, df)
    assert any("missing columns" in r.message for r in caplog.records)
