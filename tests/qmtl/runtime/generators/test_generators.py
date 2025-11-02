import pandas as pd
import pytest

from qmtl.runtime.generators import GarchInput, HestonInput, RoughBergomiInput
from qmtl.runtime.pipeline.pipeline import Pipeline
from qmtl.runtime.sdk.node import Node
from qmtl.runtime.transforms import identity_transform_node
from qmtl.runtime.sdk.util import parse_interval


@pytest.mark.parametrize(
    "generator_cls",
    [GarchInput, HestonInput, RoughBergomiInput],
)
def test_synthetic_generators_stream_through_pipeline(generator_cls):
    """Generators should honour StreamInput contracts when wired into a DAG."""

    generator = generator_cls(interval="1s", period=3, seed=7)
    outputs: list[pd.DataFrame] = []

    def collecting_transform(view):
        frame = identity_transform_node(view)
        outputs.append(frame)
        return frame

    sink = Node(
        input=generator,
        compute_fn=collecting_transform,
        interval="1s",
        period=3,
    )
    pipeline = Pipeline([generator, sink])

    timestamps: list[int] = []
    payloads: list[dict[str, float]] = []

    for _ in range(3):
        ts, payload = generator.step()
        timestamps.append(ts)
        payloads.append(payload)
        pipeline.feed(generator, ts, payload)

    assert timestamps == [parse_interval("1s"), 2 * parse_interval("1s"), 3 * parse_interval("1s")]
    assert all("price" in payload for payload in payloads)

    # Warm-up should finish once the cache has the configured period of data.
    assert sink.pre_warmup is False
    assert sink.cache.ready()

    assert len(outputs) == 1
    latest = outputs[-1]
    assert list(latest.columns) == ["price"]
    assert latest.shape == (3, 1)
    assert latest.iloc[-1]["price"] == pytest.approx(payloads[-1]["price"])
