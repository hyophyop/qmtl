import math

import pytest

from qmtl.runtime.pipeline.pipeline import Pipeline
from qmtl.runtime.sdk.node import Node, SourceNode
from qmtl.runtime.transforms import volume_features


@pytest.mark.parametrize(
    "samples, expected",
    [
        (
            [
                (1, 10.0),
                (2, 12.0),
                (3, 8.0),
                (4, 14.0),
            ],
            [
                {"volume_hat": 10.0, "volume_std": math.sqrt(8 / 3)},
                {
                    "volume_hat": pytest.approx(34 / 3),
                    "volume_std": pytest.approx(math.sqrt(56 / 9)),
                },
            ],
        ),
    ],
)
def test_volume_features_pipeline_contract(samples, expected):
    """Volume features should emit aggregates once the cache is primed."""

    source = SourceNode(interval="1s", period=3, config={"id": "vol"})
    features = volume_features(source, period=3)

    collected: list[dict[str, float]] = []

    def capture(view):
        records = view[features][features.interval]
        latest = records.latest()
        assert latest is not None
        collected.append(latest[1])
        return latest[1]

    sink = Node(
        input=features,
        compute_fn=capture,
        interval="1s",
        period=1,
    )
    pipeline = Pipeline([source, features, sink])

    for ts, volume in samples:
        pipeline.feed(source, ts, volume)

    assert len(collected) == len(expected)
    for actual, expected_payload in zip(collected, expected, strict=True):
        assert actual["volume_hat"] == pytest.approx(expected_payload["volume_hat"])
        assert actual["volume_std"] == pytest.approx(expected_payload["volume_std"])

    assert features.cache.missing_flags()[source.node_id][features.interval] is False
