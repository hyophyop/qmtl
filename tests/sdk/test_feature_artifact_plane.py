from __future__ import annotations

import pathlib

import pytest

from qmtl.sdk.feature_store import FeatureStoreConfig
from qmtl.sdk.node import Node, StreamInput
from qmtl.sdk.runner import Runner
from qmtl.sdk.strategy import Strategy


def _make_strategy(call_log: list[str]):
    class _Strategy(Strategy):
        def setup(self) -> None:
            source = StreamInput(tags=["price"], interval="1m", period=1)

            def compute(cache_view):
                call_log.append("compute")
                seq = cache_view[source][source.interval]
                ts, payload = seq.latest()
                return {"ts": ts, "value": payload["price"] * 2}

            feature = Node(
                input=source,
                compute_fn=compute,
                interval="1m",
                period=1,
                feature_plane={
                    "factor": "double_price",
                    "instrument": "BTC-USD",
                    "params": {"window": 1},
                },
            )
            self.source = source
            self.feature = feature
            self.add_nodes([source, feature])

    return _Strategy


@pytest.fixture(autouse=True)
def _reset_feature_store(tmp_path: pathlib.Path):
    Runner.reset_feature_store()
    Runner.configure_feature_store(FeatureStoreConfig(base_path=str(tmp_path)))
    yield
    Runner.reset_feature_store()


def test_feature_artifact_reused_across_domains():
    dataset_fp = "lake:blake3:test"
    timestamp = 600

    backtest_calls: list[str] = []
    BacktestStrategy = _make_strategy(backtest_calls)
    strategy_back = Runner._prepare(BacktestStrategy)
    source_back = strategy_back.source
    feature_back = strategy_back.feature

    with Runner.feature_context(
        execution_domain="backtest", dataset_fingerprint=dataset_fp, world_id="w"
    ):
        result_back = Runner.feed_queue_data(
            feature_back,
            source_back.node_id,
            source_back.interval,
            timestamp,
            {"price": 5.0},
        )

    assert backtest_calls == ["compute"]
    assert result_back == {"ts": timestamp, "value": 10.0}

    store = Runner.get_feature_store()
    assert store is not None

    live_calls: list[str] = []
    LiveStrategy = _make_strategy(live_calls)
    strategy_live = Runner._prepare(LiveStrategy)
    source_live = strategy_live.source
    feature_live = strategy_live.feature

    with Runner.feature_context(
        execution_domain="live", dataset_fingerprint=dataset_fp, world_id="w"
    ):
        result_live = Runner.feed_queue_data(
            feature_live,
            source_live.node_id,
            source_live.interval,
            timestamp,
            {"price": 1000.0},
        )

    # Live domain should reuse the backtest artifact and skip compute
    assert live_calls == []
    assert result_live == {"ts": timestamp, "value": 10.0}
